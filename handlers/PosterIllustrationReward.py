from proto.net_pb2 import ItemDetail

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PosterIllustrationRewardReq,
    PosterIllustrationRewardRsp,
    StatusCode,
    RewardStatus,
    EBagItemTag,
)
import utils.db as db
from utils.res_loader import res
from utils import item_mgr
from utils import achieve_track

"""
# 映像图鉴领奖 1425 1426
须已拥有对应映像; 奖励按映像品质取
GlobalConfig.Gacha_Poster_Quality{quality}_Reward("货币:数量")。
领取状态持久化 claimed_rewards(system=poster_illustration)。
"""


@packet_handler(MsgId.PosterIllustrationRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PosterIllustrationRewardReq()
        req.ParseFromString(data)

        rsp = PosterIllustrationRewardRsp()

        # illustration -> 任一对应 poster 的 item_i_d(取品质)
        quality = None
        for row in res["Poster"]["poster"]["datas"]:
            if (
                isinstance(row, dict)
                and row.get("illustration_i_d") == req.poster_illustration_id
            ):
                item_cfg = next(
                    (
                        e
                        for e in res["Item"]["item"]["datas"]
                        if isinstance(e, dict) and e.get("i_d") == row.get("item_i_d")
                    ),
                    None,
                )
                if item_cfg:
                    quality = int(item_cfg.get("quality", 1))
                break
        if quality is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.PosterIllustrationRewardRsp, rsp, packet_id)
            return

        # 是否拥有该映像任一实例
        owned = False
        for blob in db.get_item_detail(session.player_id, table="items_s"):

            d = ItemDetail()
            d.ParseFromString(blob)
            if d.main_item.item_tag == EBagItemTag.EBagItemTag_Poster and any(
                isinstance(r2, dict)
                and r2.get("item_i_d") == d.main_item.poster.poster_id
                and r2.get("illustration_i_d") == req.poster_illustration_id
                for r2 in res["Poster"]["poster"]["datas"]
            ):
                owned = True
                break

        if not db.try_claim(
            session.player_id, "poster_illustration", str(req.poster_illustration_id)
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.PosterIllustrationRewardRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        rsp.poster_illustration.poster_illustration_id = req.poster_illustration_id
        rsp.poster_illustration.status = RewardStatus.Reward

        # 奖励: Gacha_Poster_Quality{q}_Reward = '货币:数量'
        key = f"Gacha_Poster_Quality{quality}_Reward"
        grants = []
        for e in res["GlobalConfig"]["config"]["datas"]:
            if e.get("key") == key:
                for pair in e.get("values", ()):
                    cid, _, num = str(pair).partition(":")
                    if cid.isdigit():
                        grants.append((int(cid), int(num or 1)))
                break
        if grants and owned:
            item_mgr.grant_items(
                session.player_id, grants, session=session, rsp_items=rsp.items
            )
        if owned:
            # 成就161: 领取映像收藏奖励。
            achieve_track.report(session, "poster_illustration_reward")

        session.send(MsgId.PosterIllustrationRewardRsp, rsp, packet_id)  # 1425,1426
