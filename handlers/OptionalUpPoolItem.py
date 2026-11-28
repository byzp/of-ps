from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import pickle

from proto.net_pb2 import (
    OptionalUpPoolItemReq,
    OptionalUpPoolItemRsp,
    StatusCode,
)

import utils.db as db
from utils import gacha_prob


@packet_handler(MsgId.OptionalUpPoolItemReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OptionalUpPoolItemReq()
        req.ParseFromString(data)

        rsp = OptionalUpPoolItemRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 自选UP物品: 持久化到 kv, 重登不丢
        db.set_kv(
            session.player_id,
            "gacha_optional_up",
            str(req.gacha_id),
            pickle.dumps({"item_id": req.item_id, "pool_id": req.poo_id}),
        )
        rsp.info.gacha_id = req.gacha_id
        rsp.info.gacha_times = db.get_total_gacha_num(session.player_id, req.gacha_id)
        info = self._info_of(req.gacha_id)
        rsp.info.guarantee = gacha_prob.remaining(
            session.player_id, req.gacha_id, self._type_of(req.gacha_id), info
        )
        rsp.info.optional_up_item = req.item_id
        rsp.info.choose_pool_id = req.poo_id

        session.send(MsgId.OptionalUpPoolItemRsp, rsp, packet_id)  # 2207,2208

    @staticmethod
    def _info_of(gacha_id):
        """取该卡池的配置行（保底抽数以 max_times 为准）。"""
        from utils.res_loader import res

        for e in res["Gacha"]["info"]["datas"]:
            if isinstance(e, dict) and e.get("i_d") == gacha_id:
                return e
        return {}

    @staticmethod
    def _type_of(gacha_id):
        """取该卡池的 UI 类型（SR / 服装等类型级保底用）。"""
        from utils.res_loader import res

        for e in res["Gacha"]["info"]["datas"]:
            if isinstance(e, dict) and e.get("i_d") == gacha_id:
                return int(e.get("new_u_i_gacha_type") or 2)
        return 2
