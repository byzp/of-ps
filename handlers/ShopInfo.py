from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as ShopInfoReq_pb2
import proto.OverField_pb2 as ShopInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.res_loader import res

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ShopInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ShopInfoReq_pb2.ShopInfoReq()
        req.ParseFromString(data)

        rsp = ShopInfoRsp_pb2.ShopInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.shop_id = req.shop_id
        logger.info("ShopInfoReq shop_id=%s", req.shop_id)
        for dat in res["Shop"]["grid"]["datas"]:
            if dat.get("i_d") == req.shop_id:
                for i in dat.get("items"):
                    tmp = rsp.grids.add()
                    tmp.id = req.shop_id
                    tmp.grid_id = i["grid_i_d"]
                    tmp.pool_id = i["shop_pool_i_d"]
                    tmp.pool_index = 1 if req.shop_id != 100 else i.get("index", 1)
        session.send(MsgId.ShopInfoRsp, rsp, packet_id)  # 1675,1676


"""
shop_id tab页
200 推荐月卡
600 星尘星砂
400 超值礼包
900 精品商店
500 星石兑换
100 充值商店
300 打折优惠
800 玩偶服
1000 ROTA积分
"""
