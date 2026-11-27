from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import GachaFullPickReq, GachaFullPickRsp, PackNotice, StatusCode
from handlers.Gacha import _configuration, _rows
import utils.db as db
from utils import item_mgr
from utils.res_loader import res


@packet_handler(MsgId.GachaFullPickReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GachaFullPickReq()
        req.ParseFromString(data)
        rsp = GachaFullPickRsp()
        configuration = _configuration(req.gacha_id)
        if configuration is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GachaFullPickRsp, rsp, packet_id)
            return
        _, normal, guarantee = configuration
        if req.item_id not in set(normal + guarantee):
            rsp.status = StatusCode.StatusCode_GACHA_ITEM_NOT_EXIST
            session.send(MsgId.GachaFullPickRsp, rsp, packet_id)
            return
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with item_mgr.player_lock(session.player_id), db.transaction():
                if db.get_total_gacha_num(session.player_id, req.gacha_id) < Config.FULL_PICK_MIN_DRAWS:
                    rsp.status = StatusCode.StatusCode_BAD_REQ
                elif not db.try_claim(session.player_id, "gacha_full_pick", f"{req.gacha_id}:{req.item_id}"):
                    rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                else:
                    character_cfg = next(
                        (row for row in _rows("Character", "character") if row.get("i_d") == req.item_id),
                        None,
                    )
                    if character_cfg:
                        item = rsp.item.add()
                        item_mgr.grant_character(session.player_id, req.item_id, item, pack_notice=pack)
                        item.extra_quality = int(character_cfg.get("quality", 0) or 0)
                        pack.items.add().CopyFrom(item)
                    else:
                        item_mgr.grant_single_item(
                            session.player_id,
                            req.item_id,
                            num=1,
                            rsp_items=rsp.item,
                            pack_notice=pack,
                        )
                    db.add_gacha_record(session.player_id, req.gacha_id, req.item_id)
                    rsp.status = StatusCode.StatusCode_OK
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.item[:]
            del pack.items[:]
        session.send(MsgId.GachaFullPickRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and pack.items:
            session.send(MsgId.PackNotice, pack, 0)
