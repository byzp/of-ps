from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config


from proto.net_pb2 import (
    CreatePayOrderReq,
    CreatePayOrderRsp,
    PaySendGoodsNotice,
    ItemDetail,
    PackNotice,
    StatusCode,
)
import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.pb_create import make_item
from server.scene_data import get_session


@packet_handler(MsgId.CreatePayOrderReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CreatePayOrderReq()
        req.ParseFromString(data)

        rsp = CreatePayOrderRsp()
        if Config.REJECT_PAYMENT:
            rsp.status = StatusCode.StatusCode_Not_Payment
            session.send(MsgId.CreatePayOrderRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        rsp.order_id = "1"
        rsp.result_str = "success"
        session.send(MsgId.CreatePayOrderRsp, rsp, packet_id)

        rsp = PaySendGoodsNotice()
        rsp.status = StatusCode.StatusCode_OK
        rsp.shop_id = req.shop_id
        rsp.order_id = "1"
        target_session = None
        target_player_id = session.player_id
        if req.to_player_id:
            rsp.to_player_id = req.to_player_id
            for session_t in get_session():
                if session_t.player_id == req.to_player_id:
                    target_session = session_t
                    target_player_id = target_session.player_id
                    break
        for data in res["Shop"]["grid"]["datas"]:
            if data["i_d"] == req.shop_id:
                rsp1 = PackNotice()
                rsp1.status = StatusCode.StatusCode_OK
                for grid in data["items"]:
                    if grid["grid_i_d"] == req.grid_id:
                        for pool in res["Shop"]["pool"]["datas"]:
                            if pool["i_d"] == grid["shop_pool_i_d"]:
                                rsp.grids.pool_id = pool["i_d"]
                                for item_pool in pool["items"]:
                                    # 实例安全发放(武器/映像单独落库)
                                    item_mgr.grant_single_item(
                                        target_player_id,
                                        item_pool["item_i_d"],
                                        num=item_pool.get("item_num", 1),
                                        pack_notice=rsp1,
                                        rsp_items=rsp.items,
                                    )
                                if req.to_player_id:
                                    if target_session:
                                        target_session.send(
                                            MsgId.PaySendGoodsNotice, rsp, 0
                                        )
                                        target_session.send(MsgId.PackNotice, rsp1, 0)
                                else:
                                    session.send(MsgId.PaySendGoodsNotice, rsp, 0)
                                    session.send(MsgId.PackNotice, rsp1, 0)
                                return
