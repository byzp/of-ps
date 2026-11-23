import utils.db as _db

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PhotoShareCopyFashionDyeReq,
    PhotoShareCopyFashionDyeRsp,
    ItemDetail,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils.res_loader import res
import server.photo_share as ps
from utils import item_mgr


@packet_handler(MsgId.PhotoShareCopyFashionDyeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PhotoShareCopyFashionDyeReq()
        req.ParseFromString(data)

        rsp = PhotoShareCopyFashionDyeRsp()

        # 把分享照片中时装的染色方案复制到自己的同款时装上
        item_b = db.get_item_detail(session.player_id, req.outfit.outfit_id)
        if not item_b or isinstance(item_b, list):
            # 自己没有这件时装
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PhotoShareCopyFashionDyeRsp, rsp, packet_id)
            return

        outfit_item = ItemDetail()
        outfit_item.ParseFromString(item_b)
        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK
        _cost = next(
            (
                e.get("values")
                for e in res["GlobalConfig"]["config"]["datas"]
                if e.get("key") == "PhotoWall_CopyDye_Currency"
            ),
            None,
        )
        if _cost:
            _cid = int(_cost[0] if isinstance(_cost, (list, tuple)) else _cost)
            _cnum = (
                int(_cost[1])
                if isinstance(_cost, (list, tuple)) and len(_cost) > 1
                else 50
            )
            if not item_mgr.consume_items(
                session.player_id,
                [(_cid, _cnum)],
                pack_notice=notice,
                session=session,
            ):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.PhotoShareCopyFashionDyeRsp, rsp, packet_id)
                return

        ds = outfit_item.main_item.outfit.dye_schemes.add()
        ds.CopyFrom(req.outfit.dye_schemes)
        ds.scheme_index = len(outfit_item.main_item.outfit.dye_schemes) - 1
        ds.is_un_lock = True
        db.set_item_detail(
            session.player_id,
            outfit_item.SerializeToString(),
            req.outfit.outfit_id,
        )

        # 分享记录的染色下载数 +1
        with ps.lock_photo:
            record = ps.photos.get(req.code)
            if record:
                record["dye_download_total"] += 1

        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.PhotoShareCopyFashionDyeRsp, rsp, packet_id)  # 2561,2562

        notice.items.add().CopyFrom(outfit_item)
        session.send(MsgId.PackNotice, notice, 0)
