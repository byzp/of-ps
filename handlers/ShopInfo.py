from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import ShopInfoReq, ShopInfoRsp, StatusCode
from utils import shop_state
from utils.res_loader import res


@packet_handler(MsgId.ShopInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ShopInfoReq()
        req.ParseFromString(data)

        rsp = ShopInfoRsp()
        rsp.shop_id = req.shop_id
        shop_cfg = None
        for dat in res["Shop"]["grid"]["datas"]:
            if dat.get("i_d") == req.shop_id:
                shop_cfg = dat
                break
        if shop_cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ShopInfoRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        for i in shop_state.grid_rows(req.shop_id) or ():
            tmp = rsp.grids.add()
            tmp.id = req.shop_id
            tmp.grid_id = i["grid_i_d"]
            tmp.pool_id = i["shop_pool_i_d"]
            tmp.pool_index = i["pool_index"]
            tmp.buy_times = shop_state.buy_times(session.player_id, i)
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
