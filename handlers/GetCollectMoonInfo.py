from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import GetCollectMoonInfoReq, GetCollectMoonInfoRsp, StatusCode
from utils.res_loader import res


@packet_handler(MsgId.GetCollectMoonInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCollectMoonInfoReq()
        req.ParseFromString(data)

        rsp = GetCollectMoonInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.scene_id = req.scene_id
        # TODO
        session.send(MsgId.GetCollectMoonInfoRsp, rsp, packet_id)
