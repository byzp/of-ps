from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import os
import time

from proto.net_pb2 import UploadPhotoShareReq, UploadPhotoShareRsp, StatusCode

import utils.db as db
import server.photo_share as ps
from utils import achieve_track


@packet_handler(MsgId.UploadPhotoShareReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UploadPhotoShareReq()
        req.ParseFromString(data)

        rsp = UploadPhotoShareRsp()

        head = 0
        character_id = 0
        head, character_id = db.get_players_info(session.player_id, "head,character_id")

        record = {
            "code": ps.new_photo_code(),
            "player_id": session.player_id,
            "player_name": session.player_name,
            "head": head or 0,
            "upload_time": int(time.time()),
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
            "weapon_id": 0,  # 拍照时的武器/时装快照客户端未上报, 置 0
        }
        # 成就: 收集照片97(世界级聚合)

        achieve_track.collection(session, "photo")
        if req.file:
            os.makedirs("data/photos", exist_ok=True)
            with open(f"data/photos/{record['code']}.bin", "wb") as f:
                f.write(req.file)

        with ps.lock_photo:
            my_num = sum(
                1 for r in ps.photos.values() if r["player_id"] == session.player_id
            )
            limit = ps.UPLOAD_MAX_BASE + ps.extra_upload_grid.get(session.player_id, 0)
            if my_num >= limit:
                rsp.status = StatusCode.StatusCode_PS_UPLOAD_LIMIT
                session.send(MsgId.UploadPhotoShareRsp, rsp, packet_id)
                return
            ps.photos[record["code"]] = record

        rsp.status = StatusCode.StatusCode_OK
        ps.fill_detail(rsp.info, record, session.player_id)
        session.send(MsgId.UploadPhotoShareRsp, rsp, packet_id)  # 2551,2552
