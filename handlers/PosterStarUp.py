from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PosterStarUpReq,
    PosterStarUpRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
    EBagItemTag,
)

import utils.db as db
from utils import achieve_track
from utils.res_loader import res


@packet_handler(MsgId.PosterStarUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PosterStarUpReq()
        req.ParseFromString(data)

        rsp = PosterStarUpRsp()
        rsp.status = StatusCode.StatusCode_OK

        if not req.poster_instance_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.PosterStarUpRsp, rsp, packet_id)
            return
        poster_b = db.get_item_detail(session.player_id, None, req.poster_instance_id)
        if not poster_b:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PosterStarUpRsp, rsp, packet_id)
            return
        poster = ItemDetail()
        poster.ParseFromString(poster_b)

        # 消耗同名映像升星, 每消耗一张 +1 星
        # 材料校验: 必须是映像、与目标同名、且未被角色佩戴
        max_star = 0
        prop_id = None
        for p in res["Poster"]["poster"]["datas"]:
            if p.get("i_d") == poster.main_item.poster.poster_id:
                prop_id = p.get("property_i_d")
                break
        for p in res["Poster"]["poster_property"]["datas"]:
            if p.get("i_d") == prop_id:
                max_star = max(
                    g.get("star", 0) for g in p.get("poster_property_group_info", ())
                )
                break
        cur_star = poster.main_item.poster.star
        if max_star and cur_star >= max_star:
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.PosterStarUpRsp, rsp, packet_id)
            return
        if max_star:
            req.cost_poster_instance_id = req.cost_poster_instance_id[
                : max_star - cur_star
            ]
        cost_num = 0
        consumed_ids = []
        for cost_id in req.cost_poster_instance_id:
            if cost_id == req.poster_instance_id:
                continue
            cost_b = db.get_item_detail(session.player_id, None, cost_id)
            if not cost_b:
                continue
            cost_item = ItemDetail()
            cost_item.ParseFromString(cost_b)
            if cost_item.main_item.item_tag != EBagItemTag.EBagItemTag_Poster:
                continue
            if (
                cost_item.main_item.poster.poster_id
                != poster.main_item.poster.poster_id
            ):
                continue
            if cost_item.main_item.poster.wearer_id:
                continue
            db.del_item_detail(session.player_id, cost_id)
            consumed_ids.append(cost_id)
            cost_num += 1
        if not cost_num:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PosterStarUpRsp, rsp, packet_id)
            return

        poster.main_item.poster.star = min(
            poster.main_item.poster.star + cost_num, max_star or 99
        )
        db.set_item_detail(
            session.player_id, poster.SerializeToString(), None, req.poster_instance_id
        )

        rsp.poster_instance_id = req.poster_instance_id
        rsp.cost_poster_instance_id.extend(consumed_ids)  # 只回填真正被消耗的材料
        rsp.star = poster.main_item.poster.star

        # 若映像已被角色佩戴, 一并返回该角色
        wearer_id = poster.main_item.poster.wearer_id
        if wearer_id:
            chr_b = db.get_characters(session.player_id, wearer_id)
            if chr_b:
                rsp.character.add().ParseFromString(chr_b[0])

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        rsp1.items.add().CopyFrom(poster)

        # 成就: 映像升星
        achieve_track.report(session, "poster_starup")
        session.send(MsgId.PosterStarUpRsp, rsp, packet_id)  # 1421,1422
        session.send(MsgId.PackNotice, rsp1, 0)
