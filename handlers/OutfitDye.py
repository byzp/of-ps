from handlers.OutfitColorantSelect import ensure_swirl

import utils.db as _db

from utils import item_mgr as _im

from utils import achieve_track

import logging

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import OutfitDyeReq, OutfitDyeRsp, PackNotice, StatusCode
from utils.res_loader import res
from utils import item_mgr

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OutfitDyeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitDyeReq()
        req.ParseFromString(data)

        rsp = OutfitDyeRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.outfit_id = req.outfit_id
        rsp.pos_color.pos = req.pos

        ensure_swirl(session)
        color_array = session.color_data[0].get_color_array(req.uvy, 5)
        if 0 < req.add_rate_color_index <= len(color_array):
            color = color_array[req.add_rate_color_index - 1]
            rsp.pos_color.red = int(color[0])
            rsp.pos_color.green = int(color[1])
            rsp.pos_color.blue = int(color[2])
        else:
            # 越界或未指定随机色索引: 回退到客户端指定颜色
            rsp.pos_color.CopyFrom(req.specify_color)
        session.color_data[2].CopyFrom(rsp.pos_color)

        # 染色保底计数: Fashion_dye_ProbabilityAdd(10) 次内必出高品质,
        # Fashion_ColoringPlan_Count(5) 为一组; 计数持久化, rsp 回显剩余进度

        cnt = int(_db.get_kv(session.player_id, "outfit_dye", "guarantee", 0) or 0)
        cnt = 0 if cnt >= 10 else cnt + 1
        _db.set_kv(session.player_id, "outfit_dye", "guarantee", cnt)
        rsp.total_guarantee_dye_num = cnt

        # 成就: 染色(如有配置)
        # 染色消耗: Fashion_DyeStuff_Num(5) × 当前选中染剂(DyeStuff)

        _raw = None
        dye_consumed = False
        for e in res["GlobalConfig"]["config"]["datas"]:
            if e.get("key") == "Fashion_DyeStuff_Num":
                _raw = e.get("values")
                break
        if _raw is not None:
            num = int(_raw[0] if isinstance(_raw, (list, tuple)) else _raw)
            colorant = int(
                _db.get_kv(session.player_id, "outfit_dye", "selected_colorant", 0) or 0
            )
            if colorant:
                rsp1 = PackNotice()
                rsp1.status = StatusCode.StatusCode_OK
                if not item_mgr.consume_items(
                    session.player_id,
                    [(colorant, num)],
                    pack_notice=rsp1,
                    session=session,
                ):
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    session.send(MsgId.OutfitDyeRsp, rsp, packet_id)
                    return
                dye_consumed = True

        if dye_consumed:

            achieve_track.report(session, "outfit_dye")
        session.send(MsgId.OutfitDyeRsp, rsp, packet_id)
        if "rsp1" in locals() and rsp1.items:
            session.send(MsgId.PackNotice, rsp1, 0)
