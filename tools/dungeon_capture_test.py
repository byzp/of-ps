"""回放真实副本请求；对照官服持久进度，另验证重登及下一难度。"""

import socket
import struct

from google.protobuf import text_format

from network.msg_id import MsgId
from proto import net_pb2 as pb


def state(message):
    return {
        name: (
            list(getattr(message, name))
            if name in ("coins", "monsters")
            else getattr(message, name)
        )
        for name in (
            "dungeon_id",
            "enter_times",
            "exit_times",
            "finish_times",
            "coins",
            "monsters",
            "all_task_finished",
            "is_open_secret_box",
        )
    }


def check(sock, capture, directory, request):
    sequence = 2000

    def send(name, req, connection=sock):
        nonlocal sequence
        sequence += 1
        packets = request(connection, name, req, directory, sequence, quiet=True)
        response = next((m for n, m in packets if n == name[:-3] + "Rsp"), None)
        assert response is not None, name
        assert response.status == pb.StatusCode_OK, (name, response)
        return response, packets

    send("ChangeSceneChannelReq", pb.ChangeSceneChannelReq(scene_id=1))
    # 主世界及其他秘境使用同种怪物，不能提前填满11110的讨伐任务。
    for index in range(4):
        send("MonsterDeadReq", pb.MonsterDeadReq(monster_id=1014, monster_index=index))
    view, _ = send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=11110))
    assert not view.task_data_lst, "主世界击杀串入了未进入秘境的任务"
    send("DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=11101, char1=101001))
    send("MonsterDeadReq", pb.MonsterDeadReq(monster_id=1014, monster_index=0))
    view, _ = send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=11101))
    assert not view.task_data_lst, "相同模板的非任务点位提前推进了讨伐进度"
    send("MonsterDeadReq", pb.MonsterDeadReq(monster_id=1205, monster_index=1))
    for index in range(1, 5):
        send("MonsterDeadReq", pb.MonsterDeadReq(monster_id=1014, monster_index=index))
        view, _ = send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=11101))
        assert {a.achieve_id: a.count for a in view.task_data_lst} == {20101013: index}
    send("MonsterDeadReq", pb.MonsterDeadReq(monster_id=1014, monster_index=1))
    view, _ = send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=11101))
    assert {a.achieve_id: a.count for a in view.task_data_lst} == {20101013: 4}
    view, _ = send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=11110))
    assert not view.task_data_lst, "其他秘境的相同怪物击杀串入了11110"
    send("DungeonExitReq", pb.DungeonExitReq())
    # 21102配置允许索引2出现1108和1104；两种怪物分别去重。
    send("DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=21102, char1=101001))
    send("MonsterDeadReq", pb.MonsterDeadReq(monster_id=1108, monster_index=2))
    view, _ = send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=21102))
    assert not view.task_data_lst
    for _ in range(2):
        send("MonsterDeadReq", pb.MonsterDeadReq(monster_id=1104, monster_index=2))
        view, _ = send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=21102))
        assert {a.achieve_id: a.count for a in view.task_data_lst} == {20102023: 1}
    send("DungeonExitReq", pb.DungeonExitReq())
    pending = {}
    active = False
    current = 0
    count = comparisons = 0
    names = {
        "DungeonViewReq",
        "DungeonEnterReq",
        "DungeonOperateReq",
        "DungeonFinishReq",
        "DungeonExitReq",
        "DungeonTaskFinishRewardReq",
    }
    points = {
        "MonsterDeadReq",
        "TreasureBoxOpenReq",
        "TreasureBoxPickupReq",
        "CollectCoinReq",
    }
    expected_tasks = None
    for path in sorted(
        capture.glob("*.txt"), key=lambda p: float(p.name.split("-")[0])
    ):
        name = path.name.split("-")[1]
        if name not in names | points and name not in pending:
            continue
        if name.endswith("Req"):
            if name in points and not active:
                continue
            req = text_format.Parse(
                path.read_text(encoding="utf-8-sig"), getattr(pb, name)()
            )
            if name == "DungeonEnterReq":
                active = True
                current = req.dungeon_id
            rsp, packets = send(name, req)
            pending[name[:-3] + "Rsp"] = rsp
            count += 1
            if name == "DungeonExitReq":
                active = False
                scene = next(m.data for n, m in packets if n == "SceneDataNotice")
                assert any(
                    d.dungeon_id == 120301 and d.finish_times == 1
                    for d in scene.dungeons
                )
            if name == "TreasureBoxOpenReq" and current == 120301:
                assert any(n == "DungeonOpenFinalBoxNotice" for n, _ in packets)
        elif name in pending:
            actual = pending.pop(name)
            expected = text_format.Parse(
                path.read_text(encoding="utf-8-sig"), getattr(pb, name)()
            )
            if hasattr(expected, "dungeon_data"):
                assert state(actual.dungeon_data) == state(expected.dungeon_data), (
                    path.name,
                    state(actual.dungeon_data),
                    state(expected.dungeon_data),
                )
                comparisons += 1
            if name == "DungeonEnterRsp":
                box_state = lambda boxes: {
                    b.index: (b.box_id, b.type, b.state) for b in boxes
                }
                assert box_state(actual.treasure_boxes) == box_state(
                    expected.treasure_boxes
                ), path.name
            if name in ("TreasureBoxOpenRsp", "TreasureBoxPickupRsp"):
                tickets = lambda rsp: sum(
                    item.main_item.base_item.num
                    for item in rsp.items
                    if item.main_item.item_id == 104
                )
                assert tickets(actual) == tickets(expected), (
                    path.name,
                    "秘境宝箱普通招募券数量",
                    tickets(actual),
                    tickets(expected),
                )
            if name == "DungeonViewRsp":
                tasks = lambda rsp: {a.achieve_id: a.count for a in rsp.task_data_lst}
                assert tasks(actual) == tasks(expected), (
                    path.name,
                    tasks(actual),
                    tasks(expected),
                )
                if actual.dungeon_data.all_task_finished:
                    expected_tasks = tasks(actual)
            if name == "CollectCoinRsp":
                assert actual.coin_index == expected.coin_index
                items = lambda rsp: [
                    (i.main_item.item_id, i.main_item.base_item.num, i.main_item.is_new)
                    for i in rsp.rewards
                ]
                assert items(actual) == items(expected)
    assert expected_tasks == {20101101: 1, 20101102: 3, 20101103: 4, 20101104: 3}

    # 不依赖领取：已经发FinishReq的材料本确实可进入下一难度。
    enter, _ = send(
        "DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=120302, char1=101001)
    )
    assert enter.dungeon_data.dungeon_id == 120302
    send("DungeonOperateReq", pb.DungeonOperateReq())
    # 同一TCP写入中连续结算、重试及退出，不能被线程池乱序执行或覆盖通关。
    burst = bytearray()
    for name, req in (
        ("DungeonOperateReq", pb.DungeonOperateReq(operate_type=1)),
        ("DungeonFinishReq", pb.DungeonFinishReq()),
        ("DungeonFinishReq", pb.DungeonFinishReq()),
        ("DungeonExitReq", pb.DungeonExitReq()),
    ):
        sequence += 1
        body = req.SerializeToString()
        head = pb.PacketHead(
            msg_id=getattr(MsgId, name), body_len=len(body), packet_id=sequence
        )
        header = head.SerializeToString()
        burst.extend(struct.pack(">H", len(header)) + header + body)
    sock.sendall(burst)
    view, packets = send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=120302))
    finishes = [m for n, m in packets if n == "DungeonFinishRsp"]
    assert [m.dungeon_data.finish_times for m in finishes] == [1, 1]
    assert view.dungeon_data.finish_times == 1
    enter, _ = send(
        "DungeonEnterReq", pb.DungeonEnterReq(dungeon_id=11110, char1=101001)
    )
    assert (
        enter.dungeon_data.all_task_finished and enter.dungeon_data.is_open_secret_box
    )
    rsp, _ = send(
        "TreasureBoxOpenReq",
        pb.TreasureBoxOpenReq(loc_type=pb.TreasureBoxLocType_DUNGEON),
    )
    assert not rsp.items, "已领取的最终宝箱不能再次生成招募券"
    rsp, packets = send(
        "TreasureBoxPickupReq",
        pb.TreasureBoxPickupReq(loc_type=pb.TreasureBoxLocType_DUNGEON, pick_index=-1),
    )
    assert not rsp.items
    assert not any(n == "PackNotice" for n, _ in packets)
    for index in (0, 1, 2):
        rsp, _ = send("CollectCoinReq", pb.CollectCoinReq(coin_index=index))
        assert not rsp.rewards, "重进重复收集不能发奖"
    send("MonsterDeadReq", pb.MonsterDeadReq(monster_id=1014, monster_index=4))
    rsp, _ = send("DungeonViewReq", pb.DungeonViewReq(dungeon_id=11110))
    assert {a.achieve_id: a.count for a in rsp.task_data_lst} == expected_tasks
    send("DungeonExitReq", pb.DungeonExitReq())

    with socket.create_connection(sock.getpeername(), timeout=5) as reconnect:
        send(
            "VerifyLoginTokenReq", pb.VerifyLoginTokenReq(sdk_uid="1000001"), reconnect
        )
        send("PlayerLoginReq", pb.PlayerLoginReq(), reconnect)
        _, packets = send("PlayerMainDataReq", pb.PlayerMainDataReq(), reconnect)
        tickets = [
            item.main_item.base_item.num
            for name, notice in packets
            if name == "PackNotice"
            for item in notice.items
            if item.main_item.item_id == 104
        ]
        assert tickets == [1], "重登背包应保留最终宝箱领取的1张普通招募券"
        scene = next(m.data for n, m in packets if n == "SceneDataNotice")
        saved = {d.dungeon_id: d for d in scene.dungeons}
        assert saved[120301].finish_times == 1
        assert saved[11110].all_task_finished
        assert list(saved[11110].coins) == [2, 1, 0]
        assert list(saved[11110].monsters) == [4, 0, 1, 2, 3]
    print(
        f"PASS: 官服{count}条副本请求，{comparisons}份进度对照；世界/秘境隔离、任务怪点位及ID去重、难度2、连续结算退出、重复收集及重登恢复",
        flush=True,
    )
