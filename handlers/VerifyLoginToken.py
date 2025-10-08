from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as VerifyLoginTokenReq_pb2
import proto.OverField_pb2 as VerifyLoginTokenRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(CmdId.VerifyLoginTokenReq)
class VerifyLoginTokenHandler(PacketHandler):
    def handle(self, session, data: bytes):
        req = VerifyLoginTokenReq_pb2.VerifyLoginTokenReq()
        req.ParseFromString(data)
        
        rsp = VerifyLoginTokenRsp_pb2.VerifyLoginTokenRsp()
        rsp.account_type = req.account_type
        rsp.device_uuid = req.device_uuid
        rsp.is_server_open = True
        rsp.sdk_uid = req.sdk_uid
        rsp.status = StatusCode_pb2.StatusCode_Ok
        rsp.user_id = 1234567
        
        session.send(CmdId.VerifyLoginTokenRsp, rsp)