import random

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    ThrowDiceReq,
    ThrowDiceRsp,
    ThrowDiceNotice,
    ThrowDiceResultNotice,
    ThrowDiceResult,
    StatusCode,
)
from server.scene_data import get_session
import time

# 同频道掷骰历史(比大小窗口): {(scene_id, channel_id): [{"t","pid","name","pips"}]}
_dice_zone_history = {}


@packet_handler(MsgId.ThrowDiceReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ThrowDiceReq()
        req.ParseFromString(data)

        rsp = ThrowDiceRsp()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.ThrowDiceRsp, rsp, packet_id)  # 2003,2004

        pips = req.pips or random.randint(1, 6)

        # 向同场景频道玩家广播掷骰子动作
        notice = ThrowDiceNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.position.CopyFrom(req.position)
        notice.pips = pips
        notice.player_name = session.player_name
        notice.dice_id = req.dice_id
        for s in get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.ThrowDiceNotice, notice, 0)  # 2006

        # 广播骰子结果: 同频道 10 秒窗口内的掷骰聚在一起比大小,
        # 最大者 Win、其余 Lose(并列最大都算 Win)
        now = time.time()
        zone_players = [
            (s2.player_id, s2.player_name)
            for s2 in get_session()
            if s2.scene_id == session.scene_id and s2.channel_id == session.channel_id
        ]
        # 收集窗口内同频道其他玩家的点数(模块内存态)
        zone_key = (session.scene_id, session.channel_id)
        _dice_zone_history[zone_key] = [
            e for e in _dice_zone_history.get(zone_key, []) if now - e["t"] <= 10
        ]
        entries = [(session.player_id, session.player_name, pips)]
        for e in reversed(_dice_zone_history[zone_key]):
            if e["pid"] != session.player_id and all(
                e["pid"] != pid for pid, _, _ in entries
            ):
                entries.append((e["pid"], e["name"], e["pips"]))
        _dice_zone_history.setdefault(zone_key, []).append(
            {
                "t": now,
                "pid": session.player_id,
                "name": session.player_name,
                "pips": pips,
            }
        )
        if len(_dice_zone_history[zone_key]) > 50:
            del _dice_zone_history[zone_key][:-50]

        max_pips = max(p for _, _, p in entries)
        result = ThrowDiceResultNotice()
        result.status = StatusCode.StatusCode_OK
        zone = result.zone_result_lst.add()
        for pid, name, pp in entries:
            r = zone.result_lst.add()
            r.dice_id = req.dice_id
            r.pips = pp
            r.player_name = name
            r.won_result = (
                ThrowDiceResult.Win if pp == max_pips else ThrowDiceResult.Lose
            )
            r.player_id = pid
        for s in get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.ThrowDiceResultNotice, result, 0)  # 2008
