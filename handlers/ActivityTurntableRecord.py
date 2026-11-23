from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityTurntableRecordReq,
    ActivityTurntableRecordRsp,
    TurntableDrawRecord,
    StatusCode,
)
import utils.db as db


@packet_handler(MsgId.ActivityTurntableRecordReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityTurntableRecordReq()
        req.ParseFromString(data)

        rsp = ActivityTurntableRecordRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.activity_id = req.activity_id

        page = req.page if req.page > 0 else 1
        rsp.page = page

        # 记录持久化到 turntable_record 表
        records, total, total_page = db.get_turntable_records(
            session.player_id, req.activity_id, page, Config.TURNTABLE_RECORD_PAGE_SIZE
        )
        rsp.total_page = total_page
        for index, item_id, item_num, draw_time in records:
            rec = rsp.records.add()
            rec.index = index
            rec.item_id = item_id
            rec.item_num = item_num
            rec.draw_time = draw_time

        session.send(MsgId.ActivityTurntableRecordRsp, rsp, packet_id)  # 2637,2638
