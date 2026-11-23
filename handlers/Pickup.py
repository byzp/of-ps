from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config

from proto.net_pb2 import (
    EBagItemTag,
    ItemDetail,
    PickupReq,
    PickupRsp,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils import achieve_track, item_mgr


@packet_handler(MsgId.PickupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PickupReq()
        req.ParseFromString(data)

        with session.drop_lock:
            self._pickup(session, req, packet_id)

    def _pickup(self, session, req, packet_id):

        rsp = PickupRsp()
        rsp.status = StatusCode.StatusCode_OK
        if req.drop_item_index not in session.drop_items:
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.PickupRsp, rsp, packet_id)
            return
        remaining = session.drop_items[req.drop_item_index]
        if req.pick_index == -1:
            indices = list(range(len(remaining)))
        elif 1 <= req.pick_index <= len(remaining):
            indices = [req.pick_index - 1]
        else:
            indices = []
        picks = []
        for index in indices:
            item = ItemDetail()
            item.ParseFromString(remaining[index])
            picks.append(item)
        instances = sum(item_mgr.needs_temp_pack(item) for item in picks)
        if len(session.temp_pack) + instances > Config.TEMP_PACK_MAX:
            rsp.status = StatusCode.StatusCode_Temp_Pack_Is_Full
            session.send(MsgId.PickupRsp, rsp, packet_id)
            return
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        with achieve_track.batch(session):
            item_mgr.pickup_rewards(session, picks, rsp.items, rsp1)
            for item in picks:
                achieve_track.report(session, "pickup", match=item.main_item.item_id)
            for index in reversed(indices):
                del remaining[index]
            if not remaining:
                del session.drop_items[req.drop_item_index]
            session.send(MsgId.PickupRsp, rsp, packet_id)
            if rsp1.items:
                session.send(MsgId.PackNotice, rsp1, 0)
