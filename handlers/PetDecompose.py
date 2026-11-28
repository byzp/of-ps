from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import PetDecomposeReq, PetDecomposeRsp, PackNotice, StatusCode

from server import character_growth as growth
from utils import item_mgr
import utils.db as db


def _pet_rewards(item_id):
    pet_cfg = next(
        (row for row in growth.rows("Pet", "pet") if row.get("i_d") == item_id),
        None,
    )
    if pet_cfg is None:
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    reward_ids = pet_cfg.get("release_reward", ())
    if isinstance(reward_ids, int):
        reward_ids = (reward_ids,)
    if not isinstance(reward_ids, (tuple, list)):
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    costs = []
    for reward_id in reward_ids:
        if not reward_id:
            continue
        group = next(
            (
                row
                for row in growth.rows("Pet", "release_reward")
                if row.get("i_d") == reward_id
            ),
            None,
        )
        entries = group.get("release_reward_item", ()) if group else ()
        if group is None or not isinstance(entries, (tuple, list)):
            raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
        for entry in entries:
            if not isinstance(entry, dict):
                raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
            costs.append(
                (
                    int(entry.get("release_reward_i_d", 0) or 0),
                    int(entry.get("release_reward_count", 0) or 0),
                )
            )
    return growth.normalize_costs(costs)


@packet_handler(MsgId.PetDecomposeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PetDecomposeReq()
        req.ParseFromString(data)
        rsp = PetDecomposeRsp(status=StatusCode.StatusCode_OK)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                if not req.pet_instance_ids or any(
                    not instance_id for instance_id in req.pet_instance_ids
                ):
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                ids = list(dict.fromkeys(req.pet_instance_ids))
                active_rows = db.get_players_info(session.player_id, "pet_instance_id")
                active_id = int(active_rows[0] or 0) if active_rows else 0
                if active_id in ids:
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                pets = []
                rewards = []
                for instance_id in ids:
                    detail = growth.load_owned_instance(session.player_id, instance_id, "pet")
                    pets.append(detail)
                    rewards.extend(_pet_rewards(detail.main_item.item_id))
                rewards = growth.normalize_costs(rewards)
                for detail in pets:
                    db.del_item_detail(
                        session.player_id, detail.main_item.pet.instance_id
                    )
                if rewards:
                    item_mgr.grant_items(
                        session.player_id,
                        rewards,
                        pack_notice=notice,
                        session=None,
                    )
                rsp.pet_instance_ids.extend(ids)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.PetDecomposeRsp, rsp, packet_id)
            return

        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        session.send(MsgId.PetDecomposeRsp, rsp, packet_id)
