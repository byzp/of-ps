from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import os
import time

from proto.net_pb2 import UploadPhotoShareReq, UploadPhotoShareRsp, StatusCode
from config import Config

import utils.db as db
import server.photo_share as ps
from utils import achieve_track

logger = logging.getLogger(__name__)


@packet_handler(MsgId.UploadPhotoShareReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UploadPhotoShareReq()
        req.ParseFromString(data)

        rsp = UploadPhotoShareRsp()
        if len(req.file) > Config.PHOTO_MAX_BYTES:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.UploadPhotoShareRsp, rsp, packet_id)
            return

        head, character_id = db.get_players_info(session.player_id, "head,character_id")
        now = int(time.time())
        today = time.strftime('%Y-%m-%d', time.localtime(now))
        temporary = None
        target = None
        record = None
        with ps.lock_photo:
            try:
                with db.transaction():
                    raw_count = db.get_kv(session.player_id, 'photo_upload_daily', today)
                    if raw_count is None:
                        today_count = sum(
                            1 for record in ps.photos.values()
                            if record["player_id"] == session.player_id
                            and time.strftime('%Y-%m-%d', time.localtime(record["upload_time"])) == today
                        )
                    else:
                        try:
                            today_count = int(raw_count)
                        except (TypeError, ValueError):
                            today_count = 0
                    if today_count >= Config.PHOTO_DAILY_UPLOAD_LIMIT:
                        rsp.status = StatusCode.StatusCode_PS_UPLOAD_LIMIT
                        session.send(MsgId.UploadPhotoShareRsp, rsp, packet_id)
                        return
                    own_photos = [
                        item for item in ps.photos.values()
                        if item["player_id"] == session.player_id
                    ]
                    limit = ps.UPLOAD_MAX_BASE + ps.extra_upload_grid.get(session.player_id, 0)
                    if len(own_photos) >= limit:
                        rsp.status = StatusCode.StatusCode_PS_UPLOAD_LIMIT
                        session.send(MsgId.UploadPhotoShareRsp, rsp, packet_id)
                        return
                    db.set_kv(session.player_id, 'photo_upload_daily', today, today_count + 1)
                    record = {
                        "code": ps.new_photo_code(),
                        "player_id": session.player_id,
                        "player_name": session.player_name,
                        "head": head or 0,
                        "upload_time": now,
                        "title": req.title,
                        "tag1": req.tag1,
                        "tag2": req.tag2,
                        "tag3": req.tag3,
                        "camera_param": req.camera_param.SerializeToString(),
                        "is_activity": req.is_activity,
                        "activity_id": 0,
                        "likes": set(),
                        "favorites": set(),
                        "dye_download_total": 0,
                        "character_id": character_id or 0,
                        "weapon_id": 0,
                    }
                    if req.file:
                        directory = "data/photos"
                        os.makedirs(directory, exist_ok=True)
                        target = os.path.join(directory, f"{record['code']}.bin")
                        temporary = target + '.tmp'
                        with open(temporary, "wb") as output:
                            output.write(req.file)
                        os.replace(temporary, target)
                    ps.photos[record["code"]] = record
            except Exception:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
                if record is not None:
                    ps.photos.pop(record["code"], None)
                    if target and os.path.exists(target):
                        os.unlink(target)
                raise

        try:
            achieve_track.collection(session, "photo")
        except Exception:
            logger.exception("Photo upload achievement update failed")
        rsp.status = StatusCode.StatusCode_OK
        ps.fill_detail(rsp.info, record, session.player_id)
        session.send(MsgId.UploadPhotoShareRsp, rsp, packet_id)
