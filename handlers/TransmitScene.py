from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import TransmitSceneReq, TransmitSceneRsp, StatusCode
from server.scene_data import get_session


@packet_handler(MsgId.TransmitSceneReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TransmitSceneReq()
        req.ParseFromString(data)

        # 传送到好友所在场景: 返回好友当前场景/频道, 客户端随后走 ChangeSceneChannel 切场景
        rsp = TransmitSceneRsp()
        rsp.status = StatusCode.StatusCode_PLAYER_NOT_FOUND
        for s in get_session():
            if s.player_id == req.friend_id:
                rsp.status = StatusCode.StatusCode_OK
                rsp.scene_id = s.scene_id
                rsp.channel_id = s.channel_id
                break
        session.send(MsgId.TransmitSceneRsp, rsp, packet_id)  # 2315,2316
