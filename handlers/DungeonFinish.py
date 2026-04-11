from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import DungeonFinishReq, DungeonFinishRsp, StatusCode
import utils.db as db


@packet_handler(MsgId.DungeonFinishReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonFinishReq()
        req.ParseFromString(data)

        rsp = DungeonFinishRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.scene_id = session.scene_id
        dg = rsp.dungeon_data
        dg.ParseFromString(db.get_dungeon(session.player_id, session.dungeon[0]))
        dg.finish_times += 1
        db.set_dungeon(session.player_id, dg.dungeon_id, dg.SerializeToString())

        session.send(MsgId.DungeonFinishRsp, rsp, packet_id)
