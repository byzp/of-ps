from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import PosterStarUpReq, PosterStarUpRsp, StatusCode, PackNotice

from server import character_growth as growth
from utils import achieve_track
import utils.db as db


@packet_handler(MsgId.PosterStarUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PosterStarUpReq()
        req.ParseFromString(data)
        rsp = PosterStarUpRsp(status=StatusCode.StatusCode_OK)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                detail = growth.load_owned_instance(
                    session.player_id, req.poster_instance_id, "poster"
                )
                poster = detail.main_item.poster
                max_star = growth.poster_max_star(poster.poster_id)
                if poster.star >= max_star:
                    raise growth.GrowthError(StatusCode.StatusCode_POSTER_MAX_STAR)
                if poster.star <= 0:
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)

                seen = set()
                consumed = []
                for cost_id in req.cost_poster_instance_id:
                    if len(consumed) >= max_star - poster.star:
                        break
                    if not cost_id or cost_id == req.poster_instance_id or cost_id in seen:
                        continue
                    seen.add(cost_id)
                    try:
                        cost = growth.load_owned_instance(session.player_id, cost_id, "poster")
                    except growth.GrowthError:
                        continue
                    state = cost.main_item.poster
                    if state.poster_id != poster.poster_id or state.wearer_id:
                        continue
                    consumed.append(cost_id)
                if not consumed:
                    raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                for cost_id in consumed:
                    db.del_item_detail(session.player_id, cost_id)
                poster.star += len(consumed)
                db.set_item_detail(
                    session.player_id, detail.SerializeToString(), None, req.poster_instance_id
                )
                rsp.poster_instance_id = req.poster_instance_id
                rsp.cost_poster_instance_id.extend(consumed)
                rsp.star = poster.star
                if poster.wearer_id:
                    character_blobs = db.get_characters(session.player_id, poster.wearer_id)
                    if character_blobs:
                        rsp.character.add().ParseFromString(character_blobs[0])
                notice.items.add().CopyFrom(detail)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.PosterStarUpRsp, rsp, packet_id)
            return

        session.send(MsgId.PosterStarUpRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        achieve_track.report(session, "poster_starup")
