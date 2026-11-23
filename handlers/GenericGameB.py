from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import GenericGameBReq, GenericGameBRsp, StatusCode
from config import Config
from utils.dungeon_reward import sync_multiplier


@packet_handler(MsgId.GenericGameBReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GenericGameBReq()
        req.ParseFromString(data)

        rsp = GenericGameBRsp()
        # 通用游戏设置同步: 确认即可(回显请求上下文)
        rsp.status = StatusCode.StatusCode_OK
        if req.generic_msg_id == Config.GENERIC_GAME_REGION_QUERY_ID:
            rsp.params.add().int_value = Config.GENERIC_GAME_REGION_ID
            session.send(MsgId.GenericGameBRsp, rsp, packet_id)
            return
        rsp.generic_msg_id = req.generic_msg_id
        rsp.params.extend(req.params)
        for _k, _v in req.param_map.items():
            rsp.param_map[_k] = _v
        match req.generic_msg_id:
            case 2:  # DUNGEON_MULTI
                if not sync_multiplier(session.player_id, req, rsp):
                    rsp.status = StatusCode.StatusCode_BAD_REQ
        session.send(MsgId.GenericGameBRsp, rsp, packet_id)  # 2303,2304
