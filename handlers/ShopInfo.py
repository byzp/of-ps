from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as ShopInfoReq_pb2
import proto.OverField_pb2 as ShopInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin
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

        for dat in res["Shop"]["grid"]["datas"]:
            if dat.get("i_d") == req.shop_id:
                for i in dat.get("items"):
                    tmp = rsp.grids.add()
                    tmp.id = req.shop_id
                    tmp.grid_id = i["grid_i_d"]
                    tmp.pool_id = i["shop_pool_i_d"]
                    tmp.pool_index = 1  # i[""]
        session.send(MsgId.ShopInfoRsp, rsp, packet_id)  # 1675,1676
