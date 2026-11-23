from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import SceneTransmitReq, SceneTransmitRsp, StatusCode
from server.scene_data import get_session


@packet_handler(MsgId.SceneTransmitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SceneTransmitReq()
        req.ParseFromString(data)

        # 传送到指定玩家所在场景: 返回目标玩家当前场景/频道, 客户端随后走 ChangeSceneChannel 切场景
        rsp = SceneTransmitRsp()
        rsp.status = StatusCode.StatusCode_PLAYER_NOT_FOUND
        for s in get_session():
            if s.player_id == req.player_id:
                rsp.status = StatusCode.StatusCode_OK
                rsp.scene_id = s.scene_id
                rsp.channel_id = s.channel_id
                rsp.channel_label = s.channel_id
                break
        session.send(MsgId.SceneTransmitRsp, rsp, packet_id)  # 2511,2512
