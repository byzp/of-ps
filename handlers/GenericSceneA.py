from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GenericSceneAReq, GenericSceneARsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GenericSceneAReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GenericSceneAReq()
        req.ParseFromString(data)

        rsp = GenericSceneARsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.generic_msg_id = req.generic_msg_id
        rsp.params.extend(req.params)
        for _k, _v in req.param_map.items():
            rsp.param_map[_k] = _v

        match req.generic_msg_id:
            case _:
                logger.info(
                    "GenericSceneAReq 未实现的 generic_msg_id=%s params=%s",
                    req.generic_msg_id,
                    req.params,
                )

        session.send(MsgId.GenericSceneARsp, rsp, packet_id)  # 2305,2306
