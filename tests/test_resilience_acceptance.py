"""Focused fault/adversarial acceptance tests for issues #83, #86, #88, #90 and #91.

Every database, photo directory and TCP endpoint is synthetic and temporary.
"""

import json
import os
import pickle
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from config import Config
from network.game_session import GameSession
from network.msg_id import MsgId
from network.packet_factory import PacketFactory
from proto.net_pb2 import (
    CreatePayOrderReq,
    IntervalRewardReq,
    ItemDetail,
    OperatePhotoShareReq,
    PacketHead,
    PhotoOperateType,
    StatusCode,
    UploadPhotoShareReq,
    UseRedemptionCodeReq,
    UseRedemptionCodeRsp,
    VerifyLoginTokenRsp,
)
import handlers.OperatePhotoShare as photo_operate
import handlers.IntervalReward as interval_reward
import handlers.UploadPhotoShare as photo_upload
import handlers.UseRedemptionCode as redeem_handler
from server import payment_security as payment
from server import photo_share
from server import redemption
from server.scene_data import _session_list as session_list, lock_session
from utils import garden_state
import utils.db as db


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.player_name = "synthetic"
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Config, "DB_PATH", str(tmp_path / "isolated.db"))
    monkeypatch.setattr(Config, "IN_MEMORY", False)
    monkeypatch.setattr(photo_share, "_autosave_started", [False])
    monkeypatch.setattr(photo_share, "_last_snapshot", [None])
    monkeypatch.setattr(photo_share, "_snapshot_valid", [True])
    monkeypatch.setattr(photo_share, "photos", {})
    monkeypatch.setattr(photo_share, "extra_upload_grid", {})
    db.exit()
    db.init()
    db.conn.execute("INSERT INTO players(player_id,player_name) VALUES(1,'p1')")
    db.conn.execute("INSERT INTO players(player_id,player_name) VALUES(2,'p2')")
    yield tmp_path
    db.exit()


def frame(msg_id, body=b"", packet_id=1):
    head = PacketHead(msg_id=msg_id, packet_id=packet_id, body_len=len(body)).SerializeToString()
    return struct.pack(">H", len(head)) + head + body


def recv_exact(sock, size):
    result = bytearray()
    while len(result) < size:
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise ConnectionError("closed")
        result.extend(chunk)
    return bytes(result)


def recv_packet(sock):
    header_len = struct.unpack(">H", recv_exact(sock, 2))[0]
    head = PacketHead.FromString(recv_exact(sock, header_len))
    return head, recv_exact(sock, head.body_len)


def tcp_pair():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client = socket.create_connection(listener.getsockname(), timeout=2)
        server, _ = listener.accept()
    client.settimeout(2)
    server.settimeout(2)
    return client, server


# #83 photo filesystem fault injection


def test_photo_delete_unlink_failure_preserves_record_and_file(isolated):
    directory = isolated / "data" / "photos"
    directory.mkdir(parents=True)
    target = directory / "123.bin"
    target.write_bytes(b"photo")
    photo_share.photos[123] = {"player_id": 1}
    session = FakeSession()
    request = OperatePhotoShareReq(code=123, operate_type=PhotoOperateType.PhotoOperateType_DEL)
    with patch.object(photo_operate.os, "unlink", side_effect=PermissionError("denied")):
        photo_operate.Handler().handle(session, request.SerializeToString(), 1)
    assert session.sent[-1][1].status == StatusCode.StatusCode_FAIL
    assert photo_share.photos[123] == {"player_id": 1}
    assert target.read_bytes() == b"photo"


def test_photo_replace_failure_rolls_back_quota_record_and_temporary(isolated):
    session = FakeSession()
    request = UploadPhotoShareReq(file=b"photo")
    today = time.strftime("%Y-%m-%d", time.localtime())
    with patch.object(photo_upload.db, "get_players_info", return_value=[41101, 101001]), \
         patch.object(photo_upload.os, "replace", side_effect=OSError("disk failure")), \
         patch.object(photo_upload.achieve_track, "collection") as achievement:
        with pytest.raises(OSError, match="disk failure"):
            photo_upload.Handler().handle(session, request.SerializeToString(), 1)
    assert photo_share.photos == {}
    assert db.get_kv(1, "photo_upload_daily", today) is None
    assert list((isolated / "data" / "photos").glob("*.tmp")) == []
    achievement.assert_not_called()


def test_corrupt_photo_snapshot_does_not_delete_files_or_overwrite_evidence(isolated):
    directory = isolated / "data" / "photos"
    directory.mkdir(parents=True)
    target = directory / "123.bin"
    target.write_bytes(b"only copy")
    corrupt = b"not a pickle snapshot"
    with patch.object(db, "get_kv", return_value=corrupt), \
         patch.object(db, "set_kv") as write, \
         patch.object(photo_share, "_start_autosave"):
        photo_share.load()
        photo_share.save()
    assert target.read_bytes() == b"only copy"
    write.assert_not_called()


def test_photo_upload_fails_closed_while_snapshot_is_unrecoverable(isolated):
    photo_share._snapshot_valid[0] = False
    session = FakeSession()
    with patch.object(photo_upload.db, "get_players_info") as lookup, \
         patch.object(photo_upload.achieve_track, "collection") as achievement:
        photo_upload.Handler().handle(session, UploadPhotoShareReq(file=b"photo").SerializeToString(), 1)
    assert session.sent[-1][1].status == StatusCode.StatusCode_SYS_ERR
    assert photo_share.photos == {}
    assert not (isolated / "data" / "photos").exists()
    lookup.assert_not_called()
    achievement.assert_not_called()


def test_photo_cleanup_failure_is_isolated_and_does_not_abort_other_cleanup(isolated):
    directory = isolated / "data" / "photos"
    directory.mkdir(parents=True)
    denied = directory / "123.bin"
    other = directory / "124.bin"
    denied.write_bytes(b"denied")
    other.write_bytes(b"orphan")
    original_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path.name == denied.name:
            raise PermissionError("denied")
        return original_unlink(path, *args, **kwargs)

    with patch.object(db, "get_kv", return_value=None), \
         patch.object(Path, "unlink", unlink), \
         patch.object(photo_share, "_start_autosave") as autosave:
        photo_share.load()
    assert denied.exists()
    assert not other.exists()
    autosave.assert_called_once()


def test_photo_save_failure_can_be_retried_without_losing_dirty_snapshot(isolated):
    photo_share.photos[1] = {"likes": {2}}
    with patch.object(db, "set_kv", side_effect=sqlite3.OperationalError("disk failure")):
        photo_share.save()
    assert photo_share._last_snapshot[0] is None
    with patch.object(db, "set_kv") as write:
        photo_share.save()
    write.assert_called_once()


# #86 payment and redemption adversarial persistence/input cases


@pytest.fixture
def payment_order(isolated, monkeypatch):
    monkeypatch.setattr(Config, "PAYMENT_ORDER_MIN_INTERVAL_SECONDS", 0, raising=False)
    secret = "payment-test-secret-" + "x" * 32
    now = 2_000_000_000
    product = payment.Product(100, 1, 150, "goods.6", ((108, 60),))
    order = payment.create_payment_order(1, 2, product, {"goods.6": 600}, secret, now)
    payload = {
        "event_id": "event-1", "order_id": order["order_id"], "player_id": 1,
        "amount_minor": 600, "currency": "CNY", "goods_id": "goods.6",
        "status": "paid", "provider_trade_no": "trade-1",
    }
    return secret, now, order, payload


@pytest.mark.parametrize("raw", [
    b'{"event_id":"event-1","event_id":"event-2"}',
    b'[]', b'null', b'\xff',
])
def test_payment_malformed_callback_never_grants(payment_order, raw):
    secret, now, _, _ = payment_order
    grants = []
    with pytest.raises(payment.PaymentError):
        payment.settle_payment_order(raw, secret, lambda *args: grants.append(args), now)
    assert grants == []


@pytest.mark.parametrize("stored", [b"not-json", b"[]", b"null"])
def test_payment_corrupt_event_fails_closed_with_controlled_error(payment_order, stored):
    secret, now, _, payload = payment_order
    db.set_kv(0, "payment_events", payload["event_id"], stored)
    grants = []
    with pytest.raises(payment.PaymentError) as caught:
        payment.settle_payment_order(payload, secret, lambda *args: grants.append(args), now)
    assert caught.value.code == "bad_request"
    assert grants == []
    order = json.loads(bytes(db.get_kv(0, "payment_orders", payload["order_id"])).decode())
    assert order["status"] == "pending"


def test_payment_same_order_different_event_and_event_reuse_conflict(payment_order):
    secret, now, order, payload = payment_order
    grants = []
    grant = lambda *args: grants.append(args)
    assert payment.settle_payment_order(payload, secret, grant, now)
    with pytest.raises(payment.PaymentError) as caught:
        payment.settle_payment_order(dict(payload, event_id="event-2"), secret, grant, now)
    assert caught.value.code == "replay"
    other = payment.create_payment_order(1, 2, payment.Product(100, 1, 150, "goods.6", ((108, 60),)), {"goods.6": 600}, secret, now)
    with pytest.raises(payment.PaymentError) as caught:
        payment.settle_payment_order(dict(payload, order_id=other["order_id"]), secret, grant, now)
    assert caught.value.code == "conflict"
    assert len(grants) == 1


def test_redemption_wrong_type_and_corrupt_counters_do_not_consume(isolated):
    db.add_redeem_code("TYPE-1234", "101:2", code_type="invite")
    assert redemption.redeem_code(1, "TYPE-1234", None, None)[0] == 1
    db.add_redeem_code("COUNT-1234", "101:2")
    db.conn.execute("UPDATE redeem_codes SET max_uses=-1 WHERE code='COUNT-1234'")
    assert redemption.redeem_code(1, "COUNT-1234", None, None)[0] == 6
    assert db.conn.execute("SELECT used FROM redeem_codes WHERE code='COUNT-1234'").fetchone()[0] == 0


def test_invite_grant_failure_rolls_back_all_relations(isolated):
    redemption.register_invite_code("OWNER-123", 1)
    with patch.object(redemption.db, "grant_rewards", side_effect=RuntimeError("grant failed")):
        with pytest.raises(RuntimeError, match="grant failed"):
            redemption.use_invite_code(2, "OWNER-123", ((104, 1),), None, None)
    assert redemption.invite_count(1) == 0
    assert db.get_kv(2, "invite", "inviter") is None
    assert db.get_kv(2, "invite", "used") is None
    assert db.get_kv(0, "invite", "relation:2") is None


def test_corrupt_invite_graph_fails_closed_without_partial_binding(isolated):
    redemption.register_invite_code("OWNER-123", 1)
    db.set_kv(1, "invite", "invitees", b"not-json")
    with pytest.raises(ValueError, match="Corrupt invite relation"):
        redemption.use_invite_code(2, "OWNER-123", ((104, 1),), None, None)
    assert db.get_kv(2, "invite", "used") is None


# #88 database corruption and crash recovery


@pytest.mark.parametrize("commit", [False, True])
def test_wal_recovers_committed_transaction_and_discards_uncommitted_after_crash(isolated, commit):
    db.exit()
    script = """
import os
from config import Config
import utils.db as db
Config.DB_PATH = os.environ['OFPS_TEST_DB']
Config.IN_MEMORY = False
db.init()
if %r:
    with db.transaction():
        db.conn.execute("INSERT INTO players(player_id,player_name) VALUES(99,'recovered')")
else:
    db.conn.execute('BEGIN IMMEDIATE')
    db.conn.execute("INSERT INTO players(player_id,player_name) VALUES(99,'uncommitted')")
os._exit(0)
""" % commit
    env = dict(os.environ, OFPS_TEST_DB=Config.DB_PATH)
    subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1], env=env, check=True, timeout=30)
    assert Path(str(Config.DB_PATH) + "-wal").exists()
    db.init()
    row = db.conn.execute("SELECT player_name FROM players WHERE player_id=99").fetchone()
    assert (row[0] if row else None) == ("recovered" if commit else None)


@pytest.mark.parametrize("in_memory", [False, True])
def test_corrupt_database_fails_closed_without_modifying_file(isolated, monkeypatch, in_memory):
    db.exit()
    path = isolated / "isolated.db"
    corrupt = b"SQLite format 3\x00" + b"broken database evidence" * 100
    path.write_bytes(corrupt)
    monkeypatch.setattr(Config, "IN_MEMORY", in_memory)
    with pytest.raises(sqlite3.DatabaseError):
        db.init()
    assert path.read_bytes() == corrupt


def test_corrupt_player_blob_is_not_silently_reset_on_restart(isolated):
    db.set_players_info(1, "unlock_functions", [1, 2])
    db.conn.execute("UPDATE players SET unlock_functions=? WHERE player_id=1", (b"broken pickle",))
    original = db.conn.execute("SELECT unlock_functions FROM players WHERE player_id=1").fetchone()[0]
    db.exit()
    db.init()
    with pytest.raises(pickle.UnpicklingError):
        db.get_unlock_functions(1)
    assert db.conn.execute("SELECT unlock_functions FROM players WHERE player_id=1").fetchone()[0] == original


# #90 replay the exact bytes over a real loopback TCP stream


def test_raw_tcp_coalesced_fragmented_redemption_replay_grants_once(isolated):
    client, server = tcp_pair()
    session = GameSession(server, ("127.0.0.1", server.getsockname()[1]))
    session_list.append(session)
    db.add_redeem_code("REPLAY-1234", "101:2")
    grants = []

    def grant(player_id, rewards, rsp_rewards, pack_notice):
        grants.append((player_id, tuple(rewards)))
        entry = rsp_rewards.add()
        entry.main_item.item_id, entry.main_item.base_item.num = rewards[0]
        pack_notice.items.add().CopyFrom(entry)

    grant_patch = patch.object(redemption.db, "grant_rewards", side_effect=grant)
    grant_patch.start()

    def process(msg_id, body, packet_id, current):
        if msg_id == MsgId.VerifyLoginTokenReq:
            current.verified = True
            current.player_id = 1
            current.player_name = "p1"
            current.send(MsgId.VerifyLoginTokenRsp, VerifyLoginTokenRsp(status=StatusCode.StatusCode_OK), packet_id)
        elif msg_id == MsgId.UseRedemptionCodeReq:
            redeem_handler.Handler().handle(current, body, packet_id)
        return True

    worker = threading.Thread(target=session.run)
    worker.start()
    process_patch = patch.object(PacketFactory, "process_packet", side_effect=process)
    process_patch.start()
    try:
        auth = frame(MsgId.VerifyLoginTokenReq)
        redemption_wire = frame(MsgId.UseRedemptionCodeReq, UseRedemptionCodeReq(code="REPLAY-1234").SerializeToString(), packet_id=2)
        client.sendall(auth + redemption_wire + redemption_wire)
        head, body = recv_packet(client)
        assert head.msg_id == MsgId.VerifyLoginTokenRsp
        responses = [(head, body)]
        responses.extend(recv_packet(client) for _ in range(3))
        assert [(head.msg_id, head.packet_id) for head, _ in responses[1:]] == [
            (MsgId.UseRedemptionCodeRsp, 2), (MsgId.PackNotice, 0),
            (MsgId.UseRedemptionCodeRsp, 2),
        ]
        assert VerifyLoginTokenRsp.FromString(responses[0][1]).status == StatusCode.StatusCode_OK
        assert UseRedemptionCodeRsp.FromString(responses[1][1]).status == StatusCode.StatusCode_OK
        assert UseRedemptionCodeRsp.FromString(responses[3][1]).status == StatusCode.StatusCode_REDEMPTION_CODE_USED
        for byte in frame(MsgId.UseRedemptionCodeReq, UseRedemptionCodeReq(code="REPLAY-1234").SerializeToString(), packet_id=3):
            client.sendall(bytes([byte]))
        head, body = recv_packet(client)
        assert head.packet_id == 3
        assert UseRedemptionCodeRsp.FromString(body).status == StatusCode.StatusCode_REDEMPTION_CODE_USED
        assert db.conn.execute("SELECT used FROM redeem_codes").fetchone()[0] == 1
    finally:
        client.close()
        session.close()
        worker.join(2)
        with lock_session:
            session_list[:] = [item for item in session_list if item is not session]
        process_patch.stop()
        grant_patch.stop()
    assert not worker.is_alive()
    assert grants == [(1, ((101, 2),))]


def test_raw_tcp_unauthenticated_redemption_replay_is_rejected_before_dispatch(isolated):
    client, server = tcp_pair()
    session = GameSession(server, ("127.0.0.1", server.getsockname()[1]))
    worker = threading.Thread(target=session.run)
    worker.start()
    try:
        with patch.object(PacketFactory, "process_packet") as process:
            wire = frame(MsgId.UseRedemptionCodeReq, UseRedemptionCodeReq(code="REPLAY-1234").SerializeToString())
            client.sendall(wire + wire)
            assert client.recv(1) == b""
            worker.join(2)
            process.assert_not_called()
        assert not worker.is_alive()
        assert db.conn.execute("SELECT COUNT(*) FROM redeem_code_uses").fetchone()[0] == 0
    finally:
        client.close()
        session.close()
        worker.join(2)


def completed_interval(member=None):
    return {
        "interval_id": 101, "create_time": 1234, "finish_time": 1000,
        "member": [] if member is None else member,
    }


def fake_interval_grant(player_id, item_id, count):
    gain = ItemDetail()
    gain.main_item.item_id = item_id
    gain.main_item.base_item.num = count
    return gain, gain


def test_interval_missing_state_or_config_cannot_grant_or_consume(isolated):
    session = FakeSession(2)
    request = IntervalRewardReq(friend_id=2).SerializeToString()
    cfg = {"need_item_i_d": 10, "captain_count": 20, "member_count": 10}
    with patch.object(interval_reward.garden_state, "interval_cfg", return_value=cfg), \
         patch.object(interval_reward.garden_state, "grant_stack_item") as grant:
        interval_reward.Handler().handle(session, request, 1)
        assert session.sent[-1][1].status == StatusCode.StatusCode_INTERVAL_NOT_FINISH
        garden_state.set_interval(2, completed_interval())
        with patch.object(interval_reward.garden_state, "interval_cfg", return_value=None):
            interval_reward.Handler().handle(session, request, 2)
        assert session.sent[-1][1].status == StatusCode.StatusCode_CFG_NOT_FOUND
        grant.assert_not_called()
    assert not db.has_claimed(2, "interval_reward", "2:1234")


def test_interval_non_member_cannot_claim_finished_friend_reward(isolated):
    garden_state.set_interval(2, completed_interval())
    session = FakeSession(1)
    with patch.object(interval_reward.garden_state, "interval_cfg", return_value={"need_item_i_d": 10, "member_count": 10}), \
         patch.object(interval_reward.garden_state, "grant_stack_item") as grant:
        interval_reward.Handler().handle(session, IntervalRewardReq(friend_id=2).SerializeToString(), 1)
    assert session.sent[-1][1].status == StatusCode.StatusCode_INTERVAL_NOT_FINISH
    grant.assert_not_called()


def test_interval_owner_and_member_rewards_are_server_derived_and_once_per_interval(isolated):
    garden_state.set_interval(2, completed_interval([{"player_id": 1, "is_reward": False}]))
    cfg = {"need_item_i_d": 10, "captain_count": 20, "member_count": 10}
    grants = []
    with patch.object(interval_reward.garden_state, "now_ms", return_value=1001), \
         patch.object(interval_reward.garden_state, "interval_cfg", return_value=cfg), \
         patch.object(interval_reward.garden_state, "grant_stack_item", side_effect=lambda *args: (grants.append(args), fake_interval_grant(*args))[1]):
        requests = ((2, 2, StatusCode.StatusCode_OK),
                    (2, 2, StatusCode.StatusCode_REPEAT_GET_REWARD),
                    (1, 2, StatusCode.StatusCode_OK),
                    (1, 2, StatusCode.StatusCode_REPEAT_GET_REWARD))
        for player_id, friend_id, expected in requests:
            session = FakeSession(player_id)
            interval_reward.Handler().handle(session, IntervalRewardReq(friend_id=friend_id).SerializeToString(), 1)
            assert session.sent[-1][1].status == expected
    assert grants == [(2, 10, 20), (1, 10, 10)]


def test_interval_grant_failure_rolls_back_owner_and_member_claims(isolated):
    garden_state.set_interval(2, completed_interval([{"player_id": 1, "is_reward": False}]))
    cfg = {"need_item_i_d": 10, "captain_count": 20, "member_count": 10}
    with patch.object(interval_reward.garden_state, "now_ms", return_value=1001), \
         patch.object(interval_reward.garden_state, "interval_cfg", return_value=cfg), \
         patch.object(interval_reward.garden_state, "grant_stack_item", side_effect=RuntimeError("grant failed")):
        for player_id in (2, 1):
            with pytest.raises(RuntimeError, match="grant failed"):
                interval_reward.Handler().handle(FakeSession(player_id), IntervalRewardReq(friend_id=2).SerializeToString(), 1)
    assert not db.has_claimed(2, "interval_reward", "2:1234")
    assert garden_state.get_interval(2)["member"][0]["is_reward"] is False


# #91 reward authority audit: selectors may choose a server row, never reward values


def test_audited_reward_handlers_do_not_grant_client_reward_lists():
    import ast

    root = Path(__file__).resolve().parents[1] / "handlers"
    audited = (
        "ActivityRecallRewardClaim.py", "ActivityInviteRewardClaim.py",
        "DungeonStarReward.py", "SupplyBoxReward.py", "Gather.py",
        "UseRedemptionCode.py", "CreatePayOrder.py", "IntervalReward.py",
    )
    forbidden = ("req.items", "req.rewards", "req.reward_item", "req.reward_list")
    for name in audited:
        source = (root / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {
                "grant_rewards", "grant_items", "grant_single_item", "grant_character",
            }:
                argument = ast.get_source_segment(source, node.args[1]) if len(node.args) > 1 else ""
                assert not any(fragment in (argument or "") for fragment in forbidden), name


def test_payment_handler_uses_server_product_reward_not_request_fields(isolated, monkeypatch):
    # The protobuf request has no reward list; even a crafted unknown field cannot
    # become the order's authoritative rewards.
    secret = "payment-test-secret-" + "x" * 32
    resources = {"Shop": {
        "grid": {"datas": [{"i_d": 100, "items": [{"grid_i_d": 1, "index": 1, "shop_pool_i_d": 150, "goods_i_d": "goods.6"}]}]},
        "pool": {"datas": [{"i_d": 150, "items": [{"index": 1, "item_i_d": 108, "item_num": 60}]}]},
    }}
    from utils import res_loader
    import handlers.CreatePayOrder as handler
    session = FakeSession()
    monkeypatch.setattr(Config, "REJECT_PAYMENT", False)
    monkeypatch.setattr(Config, "PAYMENT_PROVIDER_ENABLED", True, raising=False)
    monkeypatch.setattr(Config, "PAYMENT_CALLBACK_SECRET", secret, raising=False)
    monkeypatch.setattr(Config, "PAYMENT_PRICES", {"goods.6": 600}, raising=False)
    monkeypatch.setattr(Config, "PAYMENT_ORDER_MIN_INTERVAL_SECONDS", 0, raising=False)
    with patch.dict(res_loader.res, resources, clear=True):
        handler.Handler().handle(session, CreatePayOrderReq(shop_id=100, grid_id=1, to_player_id=2).SerializeToString(), 1)
    assert session.sent[-1][1].status == StatusCode.StatusCode_OK
    stored = json.loads(bytes(db.get_kv(0, "payment_orders", session.sent[-1][1].order_id)).decode())
    assert stored["rewards"] == [[108, 60]]
