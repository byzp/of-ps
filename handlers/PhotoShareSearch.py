from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PhotoShareSearchReq,
    PhotoShareSearchRsp,
    PhotoSearchType,
    PhotoSearchTextType,
    StatusCode,
)

import server.photo_share as ps
import utils.db as db


@packet_handler(MsgId.PhotoShareSearchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PhotoShareSearchReq()
        req.ParseFromString(data)

        rsp = PhotoShareSearchRsp()
        rsp.status = StatusCode.StatusCode_OK

        with ps.lock_photo:
            records = list(ps.photos.values())

            if req.search_type == PhotoSearchType.PhotoSearchType_MY_SHARE:
                records = [r for r in records if r["player_id"] == session.player_id]
            elif req.search_type == PhotoSearchType.PhotoSearchType_MY_FAVORITE:
                records = [r for r in records if session.player_id in r["favorites"]]
            elif req.search_type in (
                PhotoSearchType.PhotoSearchType_SEARCH,
                PhotoSearchType.PhotoSearchType_SEARCH_PAGE,
            ):
                if req.text_type == PhotoSearchTextType.PhotoSearchTextType_CODE:
                    code = int(req.text) if req.text.isdigit() else 0
                    records = [r for r in records if r["code"] == code]
                elif req.text_type == PhotoSearchTextType.PhotoSearchTextType_UID:
                    uid = int(req.text) if req.text.isdigit() else 0
                    records = [r for r in records if r["player_id"] == uid]
                else:  # 按标题/标签模糊搜索
                    text = req.text
                    records = [
                        r
                        for r in records
                        if text
                        and (
                            text in r["title"]
                            or text in r["tag1"]
                            or text in r["tag2"]
                            or text in r["tag3"]
                            or text in r["player_name"]
                        )
                    ]
            elif req.search_type in (
                PhotoSearchType.PhotoSearchType_Activity,
                PhotoSearchType.PhotoSearchType_Activity_Rank,
            ):
                records = [r for r in records if r["is_activity"]]

            # TODAY/TOTAL 按点赞数排, NEW/其他按时间倒序
            if req.search_type in (
                PhotoSearchType.PhotoSearchType_TODAY,
                PhotoSearchType.PhotoSearchType_TOTAL,
                PhotoSearchType.PhotoSearchType_Activity_Rank,
            ):
                records.sort(
                    key=lambda r: (len(r["likes"]), r["upload_time"]), reverse=True
                )
            else:
                records.sort(key=lambda r: r["upload_time"], reverse=True)

            rsp.total_num = len(records)
            start = req.start_index
            end = req.end_index if req.end_index else len(records)
            page = records[start:end] if start < len(records) else []
            for r in page:
                if req.search_type in (
                    PhotoSearchType.PhotoSearchType_Activity,
                    PhotoSearchType.PhotoSearchType_Activity_Rank,
                ):
                    ps.fill_preview(rsp.activity_photos.add(), r, session.player_id)
                else:
                    ps.fill_preview(rsp.photos.add(), r, session.player_id)
            rsp.end_index = start + len(page)
            rsp.today_upload_limit = ps.TODAY_UPLOAD_LIMIT
            rsp.upload_max_num = ps.UPLOAD_MAX_BASE + ps.extra_upload_grid.get(
                session.player_id, 0
            )

        session.send(MsgId.PhotoShareSearchRsp, rsp, packet_id)  # 2555,2556
