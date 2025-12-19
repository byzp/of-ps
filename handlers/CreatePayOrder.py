from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config
import logging

import proto.OverField_pb2 as CreatePayOrderReq_pb2
import proto.OverField_pb2 as CreatePayOrderRsp_pb2
import proto.OverField_pb2 as PaySendGoodsNotice_pb2
import proto.OverField_pb2 as ItemDetail
import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item
from server.scene_data import get_session

logger = logging.getLogger(__name__)


@packet_handler(MsgId.CreatePayOrderReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CreatePayOrderReq_pb2.CreatePayOrderReq()
        req.ParseFromString(data)

        rsp = CreatePayOrderRsp_pb2.CreatePayOrderRsp()
        if Config.REJECT_PAYMENT:
            rsp.status = StatusCode_pb2.StatusCode_NOT_PAYMENT
            session.send(MsgId.CreatePayOrderRsp, rsp, packet_id)
            return
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.order_id = "1"
        rsp.result_str = "success"
        session.send(MsgId.CreatePayOrderRsp, rsp, packet_id)

        rsp = PaySendGoodsNotice_pb2.PaySendGoodsNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
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
            if data["i_d"] == req.shop_id:  # TODO 如果含有武器, 可能引起严重错误
                rsp1 = PackNotice_pb2.PackNotice()
                rsp1.status = StatusCode_pb2.StatusCode_OK
                for items in data["items"]:
                    if items["grid_i_d"] == req.grid_id:
                        for pool in res["Shop"]["pool"]["datas"]:
                            if pool["i_d"] == items["shop_pool_i_d"]:
                                rsp.grids.pool_id = pool["i_d"]
                                for item_pool in pool["items"]:
                                    item = db.get_item_detail(
                                        target_player_id, item_pool["item_i_d"]
                                    )
                                    tmp1 = ItemDetail.ItemDetail()
                                    if not item:
                                        item = make_item(
                                            item_pool["item_i_d"],
                                            0,
                                            target_player_id,
                                        )
                                    tmp1.ParseFromString(item)
                                    num_t = tmp1.main_item.base_item.num
                                    tmp1.main_item.base_item.num = item_pool["item_num"]
                                    rsp.items.add().CopyFrom(tmp1)
                                    tmp1.main_item.base_item.num = (
                                        num_t + item_pool["item_num"]
                                    )
                                    rsp1.items.add().CopyFrom(
                                        tmp1
                                    )  # TODO 目前是直接给礼包，不会自动开启
                                    db.set_item_detail(
                                        target_player_id,
                                        tmp1.SerializeToString(),
                                        item_pool["item_i_d"],
                                        None,
                                    )
        if req.to_player_id:
            if target_session:
                target_session.send(MsgId.PaySendGoodsNotice, rsp, 0)
                target_session.send(MsgId.PackNotice, rsp1, 0)
        else:
            session.send(MsgId.PaySendGoodsNotice, rsp, 0)
            session.send(MsgId.PackNotice, rsp1, 0)
