from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    PosterIllustrationRewardReq,
    PosterIllustrationRewardRsp,
    StatusCode,
    RewardStatus,
    ItemDetail,
)

from server import character_growth as growth
from utils import achieve_track, item_mgr
import utils.db as db


def _poster_item_ids(illustration_id):
    ids = {
        int(row.get("item_i_d", 0) or 0)
        for row in growth.rows("Poster", "poster")
        if row.get("illustration_i_d") == illustration_id
    }
    return ids - {0}


def _owned(player_id, illustration_id, poster_ids):
    for blob in db.get_item_detail(player_id, table="items_s"):
        detail = ItemDetail()
        try:
            detail.ParseFromString(blob)
        except Exception:
            continue
        if detail.main_item.WhichOneof("item") != "poster":
            continue
        poster = detail.main_item.poster
        if (
            poster.poster_id in poster_ids
            and poster.instance_id > 0
            and detail.main_item.item_id == poster.poster_id
        ):
            return True
    return False


def _reward(illustration_id):
    poster_ids = _poster_item_ids(illustration_id)
    if not poster_ids:
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    quality = None
    for poster_id in poster_ids:
        cfg = growth.item_config(poster_id)
        if cfg is not None:
            quality = int(cfg.get("quality", 1) or 1)
            break
    if quality is None:
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    key = f"Gacha_Poster_Quality{quality}_Reward"
    entry = next(
        (row for row in growth.rows("GlobalConfig", "config") if row.get("key") == key),
        None,
    )
    grants = []
    for pair in (entry.get("values", ()) if entry else ()):
        item_id, separator, count = str(pair).partition(":")
        if separator and item_id.isdigit():
            grants.append((int(item_id), int(count or 1)))
    return growth.normalize_costs(grants)


@packet_handler(MsgId.PosterIllustrationRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PosterIllustrationRewardReq()
        req.ParseFromString(data)
        rsp = PosterIllustrationRewardRsp(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                poster_ids = _poster_item_ids(req.poster_illustration_id)
                grants = _reward(req.poster_illustration_id)
                if not grants or not _owned(
                    session.player_id, req.poster_illustration_id, poster_ids
                ):
                    raise growth.GrowthError(
                        StatusCode.StatusCode_POSTER_ILLUSTRATION_NOT_ACTIVE
                    )
                if not db.try_claim(
                    session.player_id,
                    "poster_illustration",
                    str(req.poster_illustration_id),
                ):
                    raise growth.GrowthError(StatusCode.StatusCode_POSTER_ILLUSTRATION_REWARDED)
                item_mgr.grant_items(
                    session.player_id, grants, rsp_items=rsp.items, session=None
                )
                rsp.poster_illustration.poster_illustration_id = req.poster_illustration_id
                rsp.poster_illustration.status = RewardStatus.Reward
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.PosterIllustrationRewardRsp, rsp, packet_id)
            return

        session.send(MsgId.PosterIllustrationRewardRsp, rsp, packet_id)
        achieve_track.report(session, "poster_illustration_reward")
