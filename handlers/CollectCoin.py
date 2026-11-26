from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import CollectCoinReq, CollectCoinRsp, StatusCode, PackNotice
from config import Config

from utils import achieve_track, dungeon_state, item_mgr
from utils.res_loader import res


@packet_handler(MsgId.CollectCoinReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with dungeon_state.player_lock(session.player_id):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = CollectCoinReq()
        req.ParseFromString(data)

        rsp = CollectCoinRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.coin_index = req.coin_index

        if not session.dungeon[0]:
            rsp.status = StatusCode.StatusCode_PlayerNotInDungeon
            session.send(MsgId.CollectCoinRsp, rsp, packet_id)
            return

        dungeon_id = session.dungeon[0]
        scene = next(
            (
                row
                for row in res["ScenesConfigAsset"]["Dungeons"]
                if row["ID"] == dungeon_id
            ),
            None,
        )
        if not scene or not any(
            row.get("Index", 0) == req.coin_index for row in scene.get("CoinInfos", ())
        ):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.CollectCoinRsp, rsp, packet_id)
            return
        dg = dungeon_state.load(session.player_id, dungeon_id)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        with achieve_track.batch(session):
            if req.coin_index not in dg.coins:
                dg.coins.append(req.coin_index)
                item_mgr.grant_items(
                    session.player_id,
                    [Config.DUNGEON_COIN_REWARD],
                    rsp_items=rsp.rewards,
                    pack_notice=pack,
                    session=session,
                )
                achieve_track.report(session, "dungeon_coin", dungeon_id=dungeon_id)
                dungeon_state.save(session, dg)
            session.send(MsgId.CollectCoinRsp, rsp, packet_id)
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
