"""启动隔离数据库和真实TCP服务，验证登录及切场景，保留回包和错误日志。"""

import argparse
import json
import logging
from pathlib import Path
import random
import socket
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cramjam import snappy
from google.protobuf import text_format
from config import Config
from network.msg_id import MsgId
from proto import net_pb2 as pb


def serve(
    directory,
    port,
    equipped=False,
    shop=False,
    dungeons=False,
    dungeon_options=False,
    badge_tree=False,
):
    Config.DB_PATH = str(directory / "player.db")
    Config.IN_MEMORY = False
    Config.GAME_SERVER_IP = "127.0.0.1"
    Config.GAME_SERVER_PORT = port
    Config.LINK_OTHER_SERVER = False
    logging.basicConfig(level=logging.INFO)
    random.seed(0)
    from utils import res_loader, db

    res_loader.init()
    db.init()
    db.get_sdk_user_info("scene_smoke", "local")
    if badge_tree:
        from utils.pb_create import make_item

        player_id = db.get_player_id(1000001)
        resource = res_loader.res["MoonStone"]
        crystals = make_item(103, 100, player_id)
        db.set_item_detail(player_id, crystals.SerializeToString(), 103, None)
        trees = {r["i_d"]: r for r in resource["stone_unlock_data"]["datas"]}
        for area in resource["stone_area_data"]["datas"]:
            nodes = badge_test_nodes(
                area["scene_i_d"],
                trees[area["unlock_i_d"]]["stone_unlock_data_group_info"],
            )
            detail = make_item(
                area["item_i_d"], sum(r["item_count"] for r in nodes), player_id
            )
            db.set_item_detail(
                player_id, detail.SerializeToString(), area["item_i_d"], None
            )
    if dungeons or dungeon_options:
        from utils.pb_create import make_item

        player_id = db.get_player_id(1000001)
        stamina = make_item(10, 210 if dungeon_options else 110, player_id)
        db.set_item_detail(player_id, stamina.SerializeToString(), 10, None)
        if dungeons:
            # 原有掉落用例需要直接进入高难度；前置流程由options用例单独验证。
            for dungeon_id in (120103, 220102):
                progress = pb.DungeonData(dungeon_id=dungeon_id, finish_times=1)
                db.set_dungeon(player_id, dungeon_id, progress.SerializeToString())
    if shop:
        from utils import refresh

        player_id = db.get_player_id(1000001)
        # 昨日已领过，今天仍可领；不改运行环境时间或真实玩家数据。
        db.set_kv(player_id, "shop_buy", f"401:d{refresh.day_index() - 1}", 1)
    if equipped:
        player_id = db.get_player_id(1000001)
        from utils.pb_create import make_item

        character = pb.Character.FromString(db.get_characters(player_id, 101001)[0])
        armor = make_item(2112005, 1, player_id, equipment_level=1)
        armor.main_item.armor.wearer_id = 101001
        armor.main_item.armor.strength_level = 2
        armor_id = armor.main_item.armor.instance_id
        db.set_item_detail(player_id, armor.SerializeToString(), None, armor_id)
        preset = character.equipment_presets[0]
        preset.armors.add(armor_id=armor_id)
        poster = make_item(11200, 1, player_id)
        poster.main_item.poster.wearer_id = 101001
        poster.main_item.poster.star = 3
        poster_id = poster.main_item.poster.instance_id
        db.set_item_detail(player_id, poster.SerializeToString(), None, poster_id)
        preset.posters.add(poster_id=poster_id)
        db.set_character(player_id, 101001, character.SerializeToString())
    from network.game_server import GameServer

    GameServer().start()


def receive_exact(sock, size):
    result = bytearray()
    while len(result) < size:
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise ConnectionError("连接提前关闭")
        result.extend(chunk)
    return bytes(result)


def request(sock, name, message, directory, sequence, quiet=False):
    mid = getattr(MsgId, name)
    body = message.SerializeToString()
    head = pb.PacketHead(msg_id=mid, body_len=len(body), packet_id=sequence)
    encoded = head.SerializeToString()
    sock.sendall(struct.pack(">H", len(encoded)) + encoded + body)
    packets = []
    sock.settimeout(8)
    while True:
        try:
            length = struct.unpack(">H", receive_exact(sock, 2))[0]
            header = pb.PacketHead.FromString(receive_exact(sock, length))
            data = receive_exact(sock, header.body_len)
            if header.flag == 1:
                data = bytes(snappy.decompress_raw(data))
            response_name = next(
                (key for key, value in vars(MsgId).items() if value == header.msg_id),
                str(header.msg_id),
            )
            cls = getattr(pb, response_name, None)
            response = cls.FromString(data) if cls else None
            if response is not None:
                (
                    directory / f"{sequence:03}-{len(packets):03}-{response_name}.txt"
                ).write_text(text_format.MessageToString(response), encoding="utf-8")
            packets.append((response_name, response))
            sock.settimeout(0.03 if quiet else 0.5)
        except socket.timeout:
            break
    summary = [(name, getattr(value, "status", None)) for name, value in packets]
    check_achievement_references(packets)
    if not quiet:
        print(name, summary, flush=True)
    return packets


def check_achievement_references(packets):
    """状态OK不代表客户端能处理回包；所有成就引用必须存在于本地资源。"""
    resource = json.loads(
        (Path(__file__).resolve().parents[1] / "resources/data/Achieve.json").read_text(
            encoding="utf-8-sig"
        )
    )
    known = {row["i_d"] for row in resource["achieve"]["datas"] if row.get("i_d")}

    def check(message, path):
        for field, value in message.ListFields():
            field_path = f"{path}.{field.name}"
            if field.message_type:
                if field.is_repeated:
                    if field.message_type.GetOptions().map_entry:
                        if field.message_type.fields_by_name["value"].message_type:
                            for child in value.values():
                                check(child, field_path)
                    else:
                        for child in value:
                            check(child, field_path)
                else:
                    check(value, field_path)
            elif field.name in ("achieve_id", "condition_id") and value:
                assert value in known, f"{field_path} 引用了不存在的成就 {value}"

    for name, message in packets:
        if message is not None:
            check(message, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--capture", type=Path)
    parser.add_argument(
        "--dungeons", action="store_true", help="验证手册金币、特训宝箱及体力扣除"
    )
    parser.add_argument(
        "--dungeon-options", action="store_true", help="验证副本前置通关、倍率与出生点"
    )
    parser.add_argument(
        "--badge-tree", action="store_true", help="验证所有星云树节点的不同星符代价"
    )
    parser.add_argument(
        "--shop", action="store_true", help="验证配置商店、每日免费礼包及限购"
    )
    parser.add_argument(
        "--tutorial-boxes",
        action="store_true",
        help="验证教学箱初始化、全领取及重进状态",
    )
    parser.add_argument(
        "--login-only", action="store_true", help="只验证首次命名和登录初始化"
    )
    parser.add_argument(
        "--equipped", action="store_true", help="准备穿戴防具及映像的隔离账号"
    )
    args = parser.parse_args()
    if args.serve:
        serve(
            args.serve,
            args.port,
            args.equipped,
            args.shop,
            args.dungeons,
            args.dungeon_options,
            args.badge_tree,
        )
        return
    directory = Path(tempfile.mkdtemp(prefix="of-scene-smoke-"))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    print("结果目录:", directory, flush=True)
    with (directory / "server.log").open("w", encoding="utf-8") as log:
        command = [
            sys.executable,
            __file__,
            "--serve",
            str(directory),
            "--port",
            str(port),
        ]
        if args.equipped:
            command.append("--equipped")
        if args.shop:
            command.append("--shop")
        if args.dungeons:
            command.append("--dungeons")
        if args.dungeon_options:
            command.append("--dungeon-options")
        if args.badge_tree:
            command.append("--badge-tree")
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None:
                    raise RuntimeError(
                        (directory / "server.log").read_text(encoding="utf-8")
                    )
                try:
                    sock = socket.create_connection(("127.0.0.1", port), timeout=1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("服务启动超时")
                    time.sleep(0.2)
            with sock:
                request(
                    sock,
                    "VerifyLoginTokenReq",
                    pb.VerifyLoginTokenReq(sdk_uid="1000001"),
                    directory,
                    1,
                )
                request(sock, "PlayerLoginReq", pb.PlayerLoginReq(), directory, 2)
                if args.capture:
                    replay(sock, args.capture, directory)
                    sock.close()
                    with socket.create_connection(
                        ("127.0.0.1", port), timeout=5
                    ) as reconnect:
                        request(
                            reconnect,
                            "VerifyLoginTokenReq",
                            pb.VerifyLoginTokenReq(sdk_uid="1000001"),
                            directory,
                            900,
                        )
                        request(
                            reconnect,
                            "PlayerLoginReq",
                            pb.PlayerLoginReq(),
                            directory,
                            901,
                        )
                        packets = request(
                            reconnect,
                            "PlayerMainDataReq",
                            pb.PlayerMainDataReq(),
                            directory,
                            902,
                        )
                        assert any(
                            n == "SceneDataNotice" for n, _ in packets
                        ), "穿防具后重新登录没有场景"
                        for index, scene_id in enumerate((1, 9999), start=903):
                            packets = request(
                                reconnect,
                                "ChangeSceneChannelReq",
                                pb.ChangeSceneChannelReq(scene_id=scene_id),
                                directory,
                                index,
                            )
                            assert any(
                                n == "SceneDataNotice" for n, _ in packets
                            ), "穿防具后切场景失败"
                    print("PASS: 推进后重新登录及场景恢复", flush=True)
                    return
                request(
                    sock,
                    "ChangeNickNameReq",
                    pb.ChangeNickNameReq(nick_name="scene_smoke"),
                    directory,
                    3,
                )
                packets = request(
                    sock, "PlayerMainDataReq", pb.PlayerMainDataReq(), directory, 4
                )
                assert any(
                    n == "SceneDataNotice" for n, _ in packets
                ), "登录没有收到SceneDataNotice"
                if args.equipped:
                    check_equipment(packets)
                if args.tutorial_boxes:
                    check_tutorial_boxes(sock, packets, directory)
                    return
                if args.shop:
                    check_shop(sock, directory)
                    return
                if args.dungeons:
                    check_dungeons(sock, directory)
                    return
                if args.dungeon_options:
                    check_dungeon_options(sock, directory)
                    return
                if args.badge_tree:
                    check_badge_tree(sock, directory)
                    return
                if args.login_only:
                    print(
                        "PASS: 新号首次命名及登录，所有成就引用存在于本地资源",
                        flush=True,
                    )
                    return
                for index, scene_id in enumerate((1, 9999, 1), start=5):
                    packets = request(
                        sock,
                        "ChangeSceneChannelReq",
                        pb.ChangeSceneChannelReq(scene_id=scene_id),
                        directory,
                        index,
                    )
                    assert any(
                        n == "SceneDataNotice" for n, _ in packets
                    ), f"场景{scene_id}没有快照"
                    assert any(
                        n == "ChangeSceneChannelRsp" and m.status == pb.StatusCode_OK
                        for n, m in packets
                    ), f"场景{scene_id}响应失败"
                    if args.equipped:
                        check_equipment(packets)
            print("PASS: 登录和三次切场景", flush=True)
        finally:
            process.terminate()
            process.wait(timeout=10)
            server_log = (directory / "server.log").read_text(encoding="utf-8")
            print(server_log, flush=True)
            if "ERROR:" in server_log or "Traceback" in server_log:
                raise AssertionError("服务端出现错误，见保存的server.log")


def badge_test_nodes(page, rows):
    representatives = {}
    for row in rows:
        if row.get("item_count", 0) > 0:
            representatives.setdefault(row["item_count"], row)
    if page == 1:
        representatives[1] = next(row for row in rows if row["box_i_d"] == 31)
    nodes = list(representatives.values())
    if page == 1:
        for box_id in (32, 11, 25, 38, 21):
            if all(row["box_i_d"] != box_id for row in nodes):
                nodes.append(next(row for row in rows if row["box_i_d"] == box_id))
    return nodes


def check_badge_tree(sock, directory):
    resource = json.loads(
        Path("resources/data/MoonStone.json").read_text(encoding="utf-8-sig")
    )
    trees = {r["i_d"]: r for r in resource["stone_unlock_data"]["datas"]}
    sequence = 100
    total = 0
    for area in resource["stone_area_data"]["datas"]:
        page, item_id = area["scene_i_d"], area["item_i_d"]
        rows = trees[area["unlock_i_d"]]["stone_unlock_data_group_info"]
        # 各世界的每种费用各测一个，包含最高4星符；page1保留二段跳回归。
        nodes = badge_test_nodes(page, rows)
        remaining = sum(row["item_count"] for row in nodes)
        selected = set()
        for row in nodes:
            cost = row["item_count"]
            sequence += 1
            packets = request(
                sock,
                "AbilityBadgePageBoxActiveReq",
                pb.AbilityBadgePageBoxActiveReq(page=page, box_id=row["box_i_d"]),
                directory,
                sequence,
            )
            rsp = next(m for n, m in packets if n == "AbilityBadgePageBoxActiveRsp")
            assert rsp.status == pb.StatusCode_OK
            remaining -= cost
            counts = [
                i.main_item.base_item.num
                for n, m in packets
                if n == "PackNotice"
                for i in m.items
                if i.main_item.item_id == item_id
            ]
            assert counts == [
                remaining
            ], f"page={page}, box={row['box_i_d']} 应扣{cost}个星符"
            if page == 1 and row["box_i_d"] == 31:
                assert any(i.main_item.item_id == 101000000 for i in rsp.items)
            expected = dict(
                Config.BADGE_NODE_REWARDS.get(page, {}).get(row["box_i_d"], ())
            )
            actual_rewards = {}
            for item in rsp.items:
                iid = item.main_item.item_id
                num = (
                    item.main_item.base_item.num
                    if item.main_item.HasField("base_item")
                    else 1
                )
                actual_rewards[iid] = actual_rewards.get(iid, 0) + num
            assert actual_rewards == expected, (
                page,
                row["box_i_d"],
                actual_rewards,
                expected,
            )
            if page == 1 and row["box_i_d"] == 32:
                assert any(
                    n == "PlayerUnlockFunctionNotice"
                    and 101000005 in m.unlock_functions
                    for n, m in packets
                ), "花园开伞缺少功能解锁通知"
            if page == 1 and row["box_i_d"] == 11:
                assert any(
                    n == "PlayerAbilityUnlockNotice" and m.ability_id == 10010
                    for n, m in packets
                ), "生命能力缺少解锁通知"
            selected.add(row["box_i_d"])
            total += 1
            sequence += 1
            repeat = request(
                sock,
                "AbilityBadgePageBoxActiveReq",
                pb.AbilityBadgePageBoxActiveReq(page=page, box_id=row["box_i_d"]),
                directory,
                sequence,
            )
            assert not any(n == "PackNotice" for n, _ in repeat), "重复激活再次扣费"
        assert remaining == 0
        blocked = next(
            row
            for row in rows
            if row.get("item_count", 0) > 0 and row["box_i_d"] not in selected
        )
        sequence += 1
        packets = request(
            sock,
            "AbilityBadgePageBoxActiveReq",
            pb.AbilityBadgePageBoxActiveReq(page=page, box_id=blocked["box_i_d"]),
            directory,
            sequence,
        )
        assert (
            next(m for n, m in packets if n == "AbilityBadgePageBoxActiveRsp").status
            == pb.StatusCode_ITEM_NOT_ENOUGH
        )
        assert not any(n == "PackNotice" for n, _ in packets)
        sequence += 1
        packets = request(
            sock,
            "AbilityBadgeListReq",
            pb.AbilityBadgeListReq(scene_id=page),
            directory,
            sequence,
        )
        rsp = next(m for n, m in packets if n == "AbilityBadgeListRsp")
        actual = next(p for p in rsp.ability_badge_pages if p.page == page)
        assert (
            set(actual.active_box_ids) == selected
        ), "失败节点不应被解锁，成功节点应保留"
    sequence += 1
    packets = request(
        sock, "PlayerAbilityListReq", pb.PlayerAbilityListReq(), directory, sequence
    )
    abilities = next(m for n, m in packets if n == "PlayerAbilityListRsp")
    assert any(a.ability_id == 10010 and a.level == 0 for a in abilities.ability_list)
    for level in (1, 2):
        sequence += 1
        packets = request(
            sock,
            "PlayerAbilityLevelUpReq",
            pb.PlayerAbilityLevelUpReq(ability_id=10010),
            directory,
            sequence,
        )
        upgraded = next(m for n, m in packets if n == "PlayerAbilityLevelUpRsp")
        assert upgraded.status == pb.StatusCode_OK and upgraded.ability.level == level
        current = 110010100 + level
        assert any(
            i.main_item.item_id == current and i.main_item.base_item.num == 1
            for i in upgraded.items
        )
        if level == 2:
            assert any(
                i.main_item.item_id == 110010101 and i.main_item.base_item.num == 0
                for n, m in packets
                if n == "PackNotice"
                for i in m.items
            )
    for quest_id, quest_type in (
        (301011, 2),
        (500101, 4),
        (520001, 7),
        (401001, 8),
        (200001, 9),
    ):
        sequence += 1
        packets = request(
            sock,
            "AcceptQuestReq",
            pb.AcceptQuestReq(quest_id=quest_id, quest_type=quest_type),
            directory,
            sequence,
        )
        accepted = next(m for n, m in packets if n == "AcceptQuestRsp")
        assert (
            accepted.status == pb.StatusCode_OK and accepted.quest.quest_id == quest_id
        )
        assert accepted.quest.conditions, f"任务{quest_id}未构造条件"
    print(
        f"PASS: 8个世界、{total}个节点费用与奖励、花园开伞/能力通知、0级能力列表、重复激活/余额不足及5类非主线接取",
        flush=True,
    )


def check_dungeon_options(sock, directory):
    sequence = 100

    def send(name, msg):
        nonlocal sequence
        sequence += 1
        packets = request(sock, name, msg, directory, sequence)
        return next(m for n, m in packets if n == name.replace("Req", "Rsp")), packets

    def set_multiple(value, dungeon_id=120101):
        rsp, _ = send(
            "GenericGameAReq",
            pb.GenericGameAReq(
                generic_msg_id=2,
                params=[
                    pb.CommonParam(int_value=dungeon_id),
                    pb.CommonParam(int_value=value),
                ],
            ),
        )
        assert rsp.status == pb.StatusCode_OK

    def pick():
        rsp, packets = send(
            "TreasureBoxPickupReq", pb.TreasureBoxPickupReq(loc_type=1, pick_index=-1)
        )
        costs = [
            i.main_item.base_item.num
            for n, m in packets
            if n == "PackNotice"
            for i in m.items
            if i.main_item.item_id == 10
        ]
        return rsp, costs

    def check_spawn(team, dungeon_id):
        config = json.loads(
            Path("resources/data/ScenesConfigAsset.json").read_text(
                encoding="utf-8-sig"
            )
        )
        born = next(r["Born"] for r in config["Dungeons"] if r["ID"] == dungeon_id)
        for index, char in enumerate((team.char1, team.char2, team.char3)):
            if char.char_id:
                for axis in ("x", "y", "z"):
                    assert getattr(char.pos, axis) == int(
                        born[index]["Position"].get(axis, 0) * 100
                    )
                    assert getattr(char.rot, axis) == int(
                        born[index]["Rotation"].get(axis, 0) * 100
                    )

    # 用户实际报错包：generic_msg_id=2, params=[120301, 2]。
    set_multiple(2, 120301)
    query, _ = send(
        "GenericGameBReq",
        pb.GenericGameBReq(generic_msg_id=2, params=[pb.CommonParam(int_value=120301)]),
    )
    assert [p.int_value for p in query.params] == [120301, 2]

    # 查看/进入均不能制造通关；拒绝进入/扫荡后仍可正常进入难度1。
    send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=120101))
    for name, msg in (
        ("DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=120102, char1=101001)),
        ("DungeonSweepReq", pb.DungeonSweepReq(dungeon_id=120102)),
    ):
        rsp, _ = send(name, msg)
        assert rsp.status == pb.StatusCode_DungeonUnlock
    rsp, _ = send(
        "DungeonEnterReq",
        pb.DungeonEnterReq(
            dungeon_id=120101,
            char1=101001,
            pos=pb.Vector3(x=12345, z=-4321),
            rot=pb.Vector3(y=19000),
        ),
    )
    assert rsp.status == pb.StatusCode_OK
    check_spawn(rsp.team, 120101)
    assert rsp.dungeon_data.pos.x == 12345 and rsp.dungeon_data.rot.y == 19000
    locked, _ = send(
        "DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=120102, char1=101001)
    )
    assert locked.status == pb.StatusCode_DungeonUnlock, "进入一次不等于通关一次"

    set_multiple(2)
    opened, _ = send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1))
    assert [(i.main_item.item_id, i.main_item.base_item.num) for i in opened.items] == [
        (1, 600),
        (191, 2),
    ]
    # 开箱后改变选项，本箱仍按双倍扣费。
    set_multiple(3)
    _, costs = pick()
    assert costs == [150]
    _, costs = pick()
    assert not costs
    finish, _ = send("DungeonFinishReq", pb.DungeonFinishReq())
    assert finish.dungeon_data.finish_times == 1, "倍率不应伪造通关次数"
    _, packets = send("DungeonExitReq", pb.DungeonExitReq())
    scene = next(m.data for n, m in packets if n == "SceneDataNotice")
    assert any(
        d.dungeon_id == 120101 and d.finish_times == 1 for d in scene.dungeons
    ), "返回大场景丢失通关记录"
    # 不同副本独立保存倍率，难度1的三倍不会影响尚未设置的难度2。
    query, _ = send(
        "GenericGameBReq",
        pb.GenericGameBReq(generic_msg_id=2, params=[pb.CommonParam(int_value=120102)]),
    )
    assert [p.int_value for p in query.params] == [120102, 1]
    set_multiple(3, 120102)
    rsp, _ = send(
        "DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=120102, char1=101001)
    )
    assert rsp.status == pb.StatusCode_OK
    check_spawn(rsp.team, 120102)
    opened, _ = send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1))
    assert [(i.main_item.item_id, i.main_item.base_item.num) for i in opened.items] == [
        (1, 900),
        (191, 6),
    ]
    _, costs = pick()
    assert costs == [60]
    rsp, _ = send("DungeonRepeatEnterReq", pb.DungeonRepeatEnterReq(char1=101001))
    check_spawn(rsp.team, 120102)
    # 三倍不足90，奖励不丢且不扣余额60。
    send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1))
    rsp, costs = pick()
    assert rsp.status == pb.StatusCode_ITEM_NOT_ENOUGH and not costs
    # 扫荡也采用当前倍率，二倍恰好扣完60，并发两份本级奖励。
    set_multiple(2, 120102)
    rsp, packets = send("DungeonSweepReq", pb.DungeonSweepReq(dungeon_id=120102))
    assert rsp.status == pb.StatusCode_OK
    assert [(i.main_item.item_id, i.main_item.base_item.num) for i in rsp.rewards] == [
        (1, 600),
        (191, 4),
    ]
    assert any(
        i.main_item.item_id == 10 and i.main_item.base_item.num == 0
        for n, m in packets
        if n == "PackNotice"
        for i in m.items
    )
    rsp, _ = send(
        "GenericGameBReq",
        pb.GenericGameBReq(generic_msg_id=2, params=[pb.CommonParam(int_value=120102)]),
    )
    assert [p.int_value for p in rsp.params] == [120102, 2]
    send("DungeonExitReq", pb.DungeonExitReq())
    send("DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=120301, char1=101001))
    opened, _ = send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1))
    assert [(i.main_item.item_id, i.main_item.base_item.num) for i in opened.items] == [
        (1, 400),
        (1000, 2),
    ]
    print(
        "PASS: 前置必须通关、双/三倍奖励及体力、箱倍率快照、扫荡倍率、进入/再次进入出生点与回城坐标",
        flush=True,
    )


def check_dungeons(sock, directory):
    sequence = 20

    def send(name, message):
        nonlocal sequence
        sequence += 1
        return request(sock, name, message, directory, sequence)

    def response(packets, name):
        return next(m for n, m in packets if n == name)

    def stamina(packets):
        values = [
            i.main_item.base_item.num
            for n, m in packets
            if n == "PackNotice"
            for i in m.items
            if i.main_item.item_id == 10
        ]
        return values[-1] if values else None

    resource = json.loads(
        (Path("resources/data/Manual.json")).read_text(encoding="utf-8-sig")
    )
    for table, field in (
        ("manual", "manual_items"),
        ("manual_dungeon", "manual_dungeon_items"),
    ):
        flag = next(f["flag_i_d"] for r in resource[table]["datas"] for f in r[field])
        packets = send("ManualFlagRewardReq", pb.ManualFlagRewardReq(flag_id=flag))
        reward = response(packets, "ManualFlagRewardRsp")
        assert [
            (i.main_item.item_id, i.main_item.base_item.num) for i in reward.items
        ] == [(101, 1000)]
        again = response(
            send("ManualFlagRewardReq", pb.ManualFlagRewardReq(flag_id=flag)),
            "ManualFlagRewardRsp",
        )
        assert again.status == pb.StatusCode_MANUAL_REWARDED and not again.items

    packets = send(
        "DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=120101, char1=101001)
    )
    boxes = response(packets, "DungeonEnterRsp").treasure_boxes
    assert (
        len(boxes) == 1
        and boxes[0].box_id == 3120101
        and boxes[0].state == pb.TreasureBoxState_Close
    )
    opened = response(
        send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1)),
        "TreasureBoxOpenRsp",
    )
    assert [(i.main_item.item_id, i.main_item.base_item.num) for i in opened.items] == [
        (1, 300),
        (191, 1),
    ]
    # 首件领取扣费；剩余领取和空领取均不再次扣费。
    packets = send(
        "TreasureBoxPickupReq", pb.TreasureBoxPickupReq(loc_type=1, pick_index=1)
    )
    assert stamina(packets) == 80
    packets = send(
        "TreasureBoxPickupReq", pb.TreasureBoxPickupReq(loc_type=1, pick_index=-1)
    )
    assert stamina(packets) is None
    packets = send(
        "TreasureBoxPickupReq", pb.TreasureBoxPickupReq(loc_type=1, pick_index=-1)
    )
    assert (
        not response(packets, "TreasureBoxPickupRsp").items and stamina(packets) is None
    )
    assert not response(
        send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1)),
        "TreasureBoxOpenRsp",
    ).items

    packets = send("DungeonSweepReq", pb.DungeonSweepReq(dungeon_id=120104))
    assert stamina(packets) == 50
    rewards = response(packets, "DungeonSweepRsp").rewards
    assert [(i.main_item.item_id, i.main_item.base_item.num) for i in rewards] == [
        (1, 300),
        (192, 4),
    ]

    # 退出重进刷新本轮箱；原session.scene_id仍为教学场景，不可误发教学金币。
    send("DungeonExitReq", pb.DungeonExitReq())
    packets = send(
        "DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=120104, char1=101001)
    )
    assert len(response(packets, "DungeonEnterRsp").treasure_boxes) == 1
    opened = response(
        send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1)),
        "TreasureBoxOpenRsp",
    )
    assert [(i.main_item.item_id, i.main_item.base_item.num) for i in opened.items] == [
        (1, 300),
        (192, 4),
    ]
    packets = send(
        "TreasureBoxPickupReq", pb.TreasureBoxPickupReq(loc_type=1, pick_index=-1)
    )
    assert stamina(packets) == 20
    packets = send("DungeonRepeatEnterReq", pb.DungeonRepeatEnterReq(char1=101001))
    boxes = response(packets, "DungeonRepeatEnterRsp").treasure_boxes
    assert len(boxes) == 1 and boxes[0].state == pb.TreasureBoxState_Close
    send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1))
    packets = send(
        "TreasureBoxPickupReq", pb.TreasureBoxPickupReq(loc_type=1, pick_index=-1)
    )
    assert (
        response(packets, "TreasureBoxPickupRsp").status
        == pb.StatusCode_ITEM_NOT_ENOUGH
    )
    assert stamina(packets) is None
    opened = response(
        send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1)),
        "TreasureBoxOpenRsp",
    )
    assert len(opened.items) == 2, "体力不足不能清空奖励"
    assert (
        response(
            send("DungeonSweepReq", pb.DungeonSweepReq(dungeon_id=120104)),
            "DungeonSweepRsp",
        ).status
        == pb.StatusCode_ITEM_NOT_ENOUGH
    )

    # 装备副本仅从该副本展示池抽取，实例等级固定由副本难度决定。
    send("DungeonExitReq", pb.DungeonExitReq())
    send("DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=220103, char1=101001))
    opened = response(
        send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1)),
        "TreasureBoxOpenRsp",
    )
    allowed = {
        i["item_i_d"]
        for r in resource["manual_show_reward"]["datas"]
        if r["i_d"] == 300102
        for i in r["manual_reward_items"]
    }
    weapons = [
        i.main_item.weapon
        for i in opened.items
        if i.main_item.WhichOneof("item") == "weapon"
    ]
    assert len(weapons) == 3 and all(
        w.weapon_id in allowed and w.level == 50 for w in weapons
    )
    send("DungeonExitReq", pb.DungeonExitReq())
    send("DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=120301, char1=101001))
    opened = response(
        send("TreasureBoxOpenReq", pb.TreasureBoxOpenReq(loc_type=1)),
        "TreasureBoxOpenRsp",
    )
    assert [(i.main_item.item_id, i.main_item.base_item.num) for i in opened.items] == [
        (1, 200),
        (1000, 1),
    ]
    packets = send(
        "TreasureBoxPickupReq", pb.TreasureBoxPickupReq(loc_type=1, pick_index=-1)
    )
    assert stamina(packets) == 0, "20体力副本不能固定扣30"
    print(
        "PASS: 两类手册解锁金币、材料难度、单箱初始化、领取一次扣费、空领去重、重进重置、体力不足保留奖励及装备副本等级",
        flush=True,
    )


def check_shop(sock, directory):
    resource = json.loads(
        (Path(__file__).resolve().parents[1] / "resources/data/Shop.json").read_text(
            encoding="utf-8-sig"
        )
    )
    pools = {row["i_d"]: row for row in resource["pool"]["datas"]}
    for sequence, shop_id in enumerate((400, 600, 100), start=10):
        packets = request(
            sock, "ShopInfoReq", pb.ShopInfoReq(shop_id=shop_id), directory, sequence
        )
        info = next(m for n, m in packets if n == "ShopInfoRsp")
        configured = next(
            row["items"] for row in resource["grid"]["datas"] if row["i_d"] == shop_id
        )
        assert [(g.grid_id, g.pool_id, g.pool_index) for g in info.grids] == [
            (
                row["grid_i_d"],
                row["shop_pool_i_d"],
                pools[row["shop_pool_i_d"]]["items"][0].get("index", 1),
            )
            for row in configured
        ], f"商店{shop_id}未完整沿用资源配置"
        if shop_id == 400:
            assert (
                next(g for g in info.grids if g.grid_id == 1).buy_times == 0
            ), "昨日购买不应占用今日次数"
    buy = pb.ShopBuyReq(shop_id=400, grid_id=1, buy_times=1, item_id=6020010)
    packets = request(sock, "ShopBuyReq", buy, directory, 20)
    response = next(m for n, m in packets if n == "ShopBuyRsp")
    assert response.status == pb.StatusCode_OK and response.grids.buy_times == 1
    assert {i.main_item.item_id: i.main_item.base_item.num for i in response.items} == {
        190: 2,
        101: 1000,
        1501: 2,
    }, "免费礼包展开与抓包不符"
    assert any(n == "PackNotice" for n, _ in packets), "礼包物品未同步客户端"
    packets = request(sock, "ShopBuyReq", buy, directory, 21)
    response = next(m for n, m in packets if n == "ShopBuyRsp")
    assert response.status == pb.StatusCode_FAIL and not response.items
    assert not any(n == "PackNotice" for n, _ in packets), "重复购买不应发奖"
    packets = request(sock, "ShopInfoReq", pb.ShopInfoReq(shop_id=400), directory, 22)
    info = next(m for n, m in packets if n == "ShopInfoRsp")
    assert next(g for g in info.grids if g.grid_id == 1).buy_times == 1
    print(
        "PASS: 商店400/600/100完整配置、昨日次数重置、免费礼包奖励、同日限购及列表已购次数",
        flush=True,
    )


def check_equipment(packets):
    scene = next(m for n, m in packets if n == "SceneDataNotice")
    player = next(p for p in scene.data.players if p.player_id == 1000001)
    armor = next(a for a in player.team.char1.armors if a.armor_id == 2112005)
    assert armor.armor_star == 2, "防具强化等级没有正确同步"
    poster = next(p for p in player.team.char1.posters if p.poster_id == 11200)
    assert poster.poster_star == 3, "映像星级没有正确同步"


def check_tutorial_boxes(sock, packets, directory):
    scene = next(m for n, m in packets if n == "SceneDataNotice")
    assert scene.data.scene_id == Config.TUTORIAL_SCENE_ID
    assert [
        (b.index, b.box_id, b.type, b.state) for b in scene.data.treasure_boxes
    ] == [
        (0, 30001, 1, pb.TreasureBoxState_Close),
        (1, 30002, 1, pb.TreasureBoxState_Close),
    ], "教学箱初始化与官服新号场景快照不一致"
    for index, item_id in ((0, 101), (1, 102)):
        packets = request(
            sock,
            "TreasureBoxOpenReq",
            pb.TreasureBoxOpenReq(treasure_box_index=index),
            directory,
            10 + index * 3,
        )
        opened = next(m for n, m in packets if n == "TreasureBoxOpenRsp")
        assert opened.status == pb.StatusCode_OK and len(opened.items) == 1
        assert opened.items[0].main_item.item_id == item_id
        assert opened.next_refresh_time == 0
        packets = request(
            sock,
            "TreasureBoxPickupReq",
            pb.TreasureBoxPickupReq(box_index=index, pick_index=-1),
            directory,
            11 + index * 3,
        )
        picked = next(m for n, m in packets if n == "TreasureBoxPickupRsp")
        assert picked.status == pb.StatusCode_OK and len(picked.items) == 1
        assert picked.items[0].main_item.item_id == item_id
        assert not any(n == "SceneDataNotice" for n, _ in packets), "领取不应重载场景"
        packets = request(
            sock,
            "TreasureBoxOpenReq",
            pb.TreasureBoxOpenReq(treasure_box_index=index),
            directory,
            12 + index * 3,
        )
        opened = next(m for n, m in packets if n == "TreasureBoxOpenRsp")
        assert opened.status == pb.StatusCode_OK and not opened.items
    packets = request(
        sock,
        "ChangeSceneChannelReq",
        pb.ChangeSceneChannelReq(scene_id=1),
        directory,
        20,
    )
    scene = next(m for n, m in packets if n == "SceneDataNotice")
    assert not scene.data.treasure_boxes, "普通世界无记录时不应初始化宝箱条目"
    packets = request(
        sock,
        "ChangeSceneChannelReq",
        pb.ChangeSceneChannelReq(scene_id=Config.TUTORIAL_SCENE_ID),
        directory,
        21,
    )
    scene = next(m for n, m in packets if n == "SceneDataNotice")
    assert len(scene.data.treasure_boxes) == 2
    assert all(
        b.state == pb.TreasureBoxState_Open
        and not b.rewards
        and not b.next_refresh_time
        for b in scene.data.treasure_boxes
    )
    print(
        "PASS: 教学双箱初始化、全领取、重复打开无奖励、重进保持开启；普通世界不补未开启条目",
        flush=True,
    )


def replay(sock, capture, directory):
    files = sorted(capture.glob("*.txt"), key=lambda p: float(p.name.split("-")[0]))
    differences = []
    total = 0
    scene_count = 0
    for file in files:
        name = file.name.split("-")[1]
        if not name.endswith("Req") or name in (
            "VerifyLoginTokenReq",
            "PlayerLoginReq",
        ):
            continue
        message = text_format.Parse(
            file.read_text(encoding="utf-8-sig"), getattr(pb, name)()
        )
        total += 1
        packets = request(sock, name, message, directory, total + 2, quiet=True)
        scene_count += sum(n == "SceneDataNotice" for n, _ in packets)
        response_name = name[:-3] + "Rsp"
        response = next((m for n, m in packets if n == response_name), None)
        expected_file = next(
            (
                p
                for p in files
                if float(p.name.split("-")[0]) > float(file.name.split("-")[0])
                and p.name.split("-")[1] == response_name
            ),
            None,
        )
        expected = (
            text_format.Parse(
                expected_file.read_text(encoding="utf-8-sig"),
                getattr(pb, response_name)(),
            )
            if expected_file
            else None
        )
        if response is None or (
            expected is not None
            and hasattr(expected, "status")
            and response.status != expected.status
        ):
            difference = {
                "request": file.name,
                "actual_status": getattr(response, "status", None),
                "expected_status": getattr(expected, "status", None),
            }
            differences.append(difference)
            print("DIFF", difference, flush=True)
        if total % 50 == 0:
            print("已重放:", total, flush=True)
    (directory / "differences.json").write_text(
        json.dumps(differences, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "完整重放请求:",
        total,
        "场景快照:",
        scene_count,
        "响应状态差异:",
        len(differences),
        flush=True,
    )


if __name__ == "__main__":
    main()
