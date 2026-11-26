from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import OutfitDyeUnlockIndexReq, OutfitDyeUnlockIndexRsp, StatusCode, PackNotice

from server import character_growth as growth
import utils.db as db


@packet_handler(MsgId.OutfitDyeUnlockIndexReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitDyeUnlockIndexReq()
        req.ParseFromString(data)
        rsp = OutfitDyeUnlockIndexRsp(status=StatusCode.StatusCode_OK)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                if req.index >= Config.MAX_DYE_SCHEME_NUM:
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                outfit = growth.load_owned_outfit(session.player_id, req.outfit_id)
                schemes = outfit.main_item.outfit.dye_schemes
                while len(schemes) <= req.index:
                    schemes.add().scheme_index = len(schemes)
                if schemes[req.index].is_un_lock:
                    pass
                else:
                    growth.consume(session.player_id, [(102, 100)], notice)
                    schemes[req.index].is_un_lock = True
                    db.set_item_detail(
                        session.player_id, outfit.SerializeToString(), req.outfit_id
                    )
                    notice.items.add().CopyFrom(outfit)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.OutfitDyeUnlockIndexRsp, rsp, packet_id)
            return

        session.send(MsgId.OutfitDyeUnlockIndexRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
