import logging
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import VerifyLoginTokenReq, VerifyLoginTokenRsp, StatusCode
import utils.db as db
from config import Config

logger = logging.getLogger(__name__)


@packet_handler(MsgId.VerifyLoginTokenReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = VerifyLoginTokenReq()
        req.ParseFromString(data)

        rsp = VerifyLoginTokenRsp()
        rsp.status = StatusCode.StatusCode_OK
        user_id = int(db.get_user_id(req.sdk_uid))
        if Config.VERIFY_TOKEN and not db.verify_sdk_user_info(
            user_id, req.login_token
        ):
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.VerifyLoginTokenRsp, rsp, packet_id)
            return

        session.verified = True
        session.player_id = db.get_player_id(user_id)
        session.player_name = db.get_players_info(session.player_id, "player_name")
        logger.info(f"Player login: {session.player_name}({session.player_id})")
        rsp.user_id = user_id
        rsp.account_type = req.account_type
        rsp.sdk_uid = req.sdk_uid
        rsp.is_server_open = True
        rsp.time_left = 4294967295
        rsp.device_uuid = req.device_uuid

        session.send(MsgId.VerifyLoginTokenRsp, rsp, packet_id)  # 1001,1002
