from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as VerifyLoginTokenReq_pb2
import proto.OverField_pb2 as VerifyLoginTokenRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db


@packet_handler(CmdId.VerifyLoginTokenReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = VerifyLoginTokenReq_pb2.VerifyLoginTokenReq()
        req.ParseFromString(data)

        rsp = VerifyLoginTokenRsp_pb2.VerifyLoginTokenRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        user_id = int(db.get_user_id(req.sdk_uid))
        if not db.verify_sdk_user_info(user_id, req.login_token):
            rsp.status = StatusCode_pb2.StatusCode_FAIL
            session.send(CmdId.VerifyLoginTokenRsp, rsp, True, packet_id)
            return

        session.player_id = db.get_player_id(user_id)
        session.player_name = db.get_player_name(session.player_id)
        rsp.user_id = user_id
        rsp.account_type = req.account_type
        rsp.sdk_uid = req.sdk_uid
        rsp.is_server_open = True
        rsp.time_left = 4294967295
        rsp.device_uuid = req.device_uuid

        session.send(CmdId.VerifyLoginTokenRsp, rsp, True, packet_id)  # 1001,1002
