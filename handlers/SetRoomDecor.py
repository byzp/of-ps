from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    SetRoomDecorReq,
    SetRoomDecorRsp,
    RoomDecorNotice,
    StatusCode,
)

import utils.db as db
from utils.res_loader import res
from server.scene_data import get_session


@packet_handler(MsgId.SetRoomDecorReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SetRoomDecorReq()
        req.ParseFromString(data)

        rsp = SetRoomDecorRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 校验: item_id 必须是已摆放家具, 且 pos_id 在 HomeItem.room_decor 配置内
        _decor_cfg = {
            d["i_d"]: d
            for d in res.get("HomeItem", {}).get("room_decor", {}).get("datas", [])
        }
        for decor in req.decor_list:
            if not decor.item_id:
                continue
            row = db.get_furniture(
                session.scene_id,
                session.channel_id,
                session.player_id,
                decor.item_id,
            )
            if not row:
                rsp.status = StatusCode.StatusCode_FURNITURE_NOT_EXIST
                session.send(MsgId.SetRoomDecorRsp, rsp, packet_id)
                return
            cfg = _decor_cfg.get(decor.decor_id)
            if cfg and decor.pos_id > len(cfg.get("pos_decor_info", ()) or ()):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.SetRoomDecorRsp, rsp, packet_id)
                return
        session.send(MsgId.SetRoomDecorRsp, rsp, packet_id)  # 2747,2748

        # 向同场景频道玩家广播房间装饰变化
        notice = RoomDecorNotice()
        notice.status = StatusCode.StatusCode_OK
        for decor in req.decor_list:
            notice.decor_list.add().CopyFrom(decor)
        for s in get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.RoomDecorNotice, notice, 0)  # 2750
