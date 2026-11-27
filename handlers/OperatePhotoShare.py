from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import os

from proto.net_pb2 import (
    OperatePhotoShareReq,
    OperatePhotoShareRsp,
    PhotoOperateType,
    StatusCode,
)

import server.photo_share as ps
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OperatePhotoShareReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OperatePhotoShareReq()
        req.ParseFromString(data)

        rsp = OperatePhotoShareRsp()
        rsp.code = req.code

        with ps.lock_photo:
            record = ps.photos.get(req.code)
            if not record:
                rsp.status = StatusCode.StatusCode_PS_NOT_EXIST
                session.send(MsgId.OperatePhotoShareRsp, rsp, packet_id)
                return

            rsp.status = StatusCode.StatusCode_OK
            match req.operate_type:
                case PhotoOperateType.PhotoOperateType_LIKE:
                    record["likes"].add(session.player_id)
                case PhotoOperateType.PhotoOperateType_LIKE_CANCEL:
                    record["likes"].discard(session.player_id)
                case PhotoOperateType.PhotoOperateType_FAVORITE:
                    record["favorites"].add(session.player_id)
                case PhotoOperateType.PhotoOperateType_FAVORITE_CANCEL:
                    record["favorites"].discard(session.player_id)
                case PhotoOperateType.PhotoOperateType_DEL:
                    if record["player_id"] == session.player_id:
                        path = os.path.join("data/photos", f"{req.code}.bin")
                        try:
                            if os.path.isfile(path):
                                os.unlink(path)
                        except OSError:
                            # Keep the record when its file cannot be removed;
                            # otherwise a later restart sees a live record whose
                            # only photo was silently lost.
                            logger.exception("Could not delete photo file %s", path)
                            rsp.status = StatusCode.StatusCode_FAIL
                        else:
                            del ps.photos[req.code]
                    else:
                        rsp.status = StatusCode.StatusCode_FAIL
                case PhotoOperateType.PhotoOperateType_MOVE:
                    if record["player_id"] != session.player_id:
                        rsp.status = StatusCode.StatusCode_FAIL
                    else:
                        record["is_activity"] = not record.get("is_activity", False)
                        if record["is_activity"]:
                            record["activity_id"] = req.activity_id
                case _:
                    logger.info(
                        "OperatePhotoShareReq 未知 operate_type=%s", req.operate_type
                    )
                    rsp.status = StatusCode.StatusCode_BAD_REQ

        session.send(MsgId.OperatePhotoShareRsp, rsp, packet_id)  # 2559,2560
