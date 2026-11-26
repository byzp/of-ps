from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import CharacterStarUpReq, CharacterStarUpRsp, StatusCode, PackNotice, ItemDetail

from server import character_growth as growth
from utils import achieve_track, item_mgr
import utils.db as db


# 升星或满星碎片兑换均在同一事务中完成，材料写入失败时不会留下半个升星结果。
@packet_handler(MsgId.CharacterStarUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterStarUpReq()
        req.ParseFromString(data)
        rsp = CharacterStarUpRsp(status=StatusCode.StatusCode_OK)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        converted = False
        try:
            with growth.transaction(session.player_id):
                character = growth.load_character(session.player_id, req.char_id)
                stage, max_star = growth.star_stage(character)
                if stage is None:
                    cfg = next(
                        row
                        for row in growth.rows("Character", "character_star")
                        if row.get("i_d") == req.char_id
                    )
                    infos = sorted(cfg.get("star_info", ()), key=lambda row: row["star"])
                    star_item_id = int(infos[-1].get("item_i_d", 0) or 0)
                    blob = db.get_item_detail(session.player_id, star_item_id)
                    if not blob:
                        raise growth.GrowthError(StatusCode.StatusCode_FAIL)
                    shard = ItemDetail()
                    shard.ParseFromString(blob)
                    shards = (
                        int(shard.main_item.base_item.num)
                        if shard.main_item.WhichOneof("item") == "base_item"
                        else 0
                    )
                    if shards <= 0:
                        raise growth.GrowthError(StatusCode.StatusCode_FAIL)
                    if not item_mgr.consume_items(
                        session.player_id, [(star_item_id, shards)], pack_notice=notice
                    ):
                        raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                    item_mgr.grant_items(
                        session.player_id, [(101, shards * 500)], rsp_items=rsp.items
                    )
                    rsp.char_id = req.char_id
                    rsp.star = max_star
                    converted = True
                else:
                    item_id = int(stage.get("item_i_d", 0) or 0)
                    count = int(stage.get("item_num", 0) or 0)
                    if item_id <= 0 or count <= 0:
                        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
                    if not growth.consume(session.player_id, [(item_id, count)], notice):
                        raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                    character.star += 1
                    growth.save_character(session.player_id, character)
                    rsp.char_id = req.char_id
                    rsp.star = character.star
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.CharacterStarUpRsp, rsp, packet_id)
            return

        session.send(MsgId.CharacterStarUpRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        if not converted:
            achieve_track.report(session, "star_up", match=rsp.star)
