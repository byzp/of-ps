from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import CollectCoinReq, CollectCoinRsp, StatusCode, DungeonData

import utils.db as db


@packet_handler(MsgId.CollectCoinReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectCoinReq()
        req.ParseFromString(data)

        rsp = CollectCoinRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.coin_index = req.coin_index

        if not session.dungeon[0]:
            rsp.status = StatusCode.StatusCode_PlayerNotInDungeon
            session.send(MsgId.CollectCoinRsp, rsp, packet_id)
            return

        # 记录当前副本内收集到的金币点位(DungeonData.coins)
        dungeon_id = session.dungeon[0]
        if dungeon_id:
            dg = DungeonData()
            blob = db.get_dungeon(session.player_id, dungeon_id)
            if blob:
                dg.ParseFromString(blob)
            dg.dungeon_id = dungeon_id
            if req.coin_index not in dg.coins:
                dg.coins.append(req.coin_index)
            db.set_dungeon(session.player_id, dungeon_id, dg.SerializeToString())

        # 金币点位掉落配置未找到, rewards 保持留空。已查表:
        session.send(MsgId.CollectCoinRsp, rsp, packet_id)  # 1341,1342
