from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import ClapReq, ClapRsp, ClapResultNotice, StatusCode
from server.scene_data import get_session


@packet_handler(MsgId.ClapReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ClapReq()
        req.ParseFromString(data)

        rsp = ClapRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.movement_id = req.movement_id
        rsp.is_cancel = req.is_cancel
        session.send(MsgId.ClapRsp, rsp, packet_id)  # 1999,2000

        # 击掌匹配: 同频道内位置距离 ≤3m 的其他举手玩家一起进入结果
        if not req.is_cancel:
            notice = ClapResultNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.movement_id = req.movement_id
            notice.matched_player_id_lst.append(session.player_id)

            def _dist2(a, b):
                return (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2

            for other in get_session():
                if other is session:
                    continue
                if (
                    other.scene_id != session.scene_id
                    or other.channel_id != session.channel_id
                ):
                    continue
                # 同频道且距离 ≤3m 的玩家视为一起击掌
                if _dist2(other.pos, session.pos) <= 9.0:
                    notice.matched_player_id_lst.append(other.player_id)
            session.send(MsgId.ClapResultNotice, notice, 0)  # 2002
