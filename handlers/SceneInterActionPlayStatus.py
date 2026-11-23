import logging

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    FurnitureDetailsInfo,
    InterActionPushType,
    SceneInterActionPlayStatusReq,
    SceneInterActionPlayStatusNotice,
    SceneInterActionPlayStatusRsp,
    StatusCode,
)
from server import scene_data as _sd
import utils.db as db

logger = logging.getLogger(__name__)


def _broadcast_interaction(session, req):
    """交互状态同步给同场景频道玩家，包含本人回显。"""

    notice = SceneInterActionPlayStatusNotice()
    notice.status = StatusCode.StatusCode_OK
    notice.action_status.CopyFrom(req.action_status)
    notice.push_type = req.push_type
    notice.player_id = session.player_id
    for s in _sd.get_session():
        if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
            s.send(MsgId.SceneInterActionPlayStatusNotice, notice, 0)


@packet_handler(MsgId.SceneInterActionPlayStatusReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SceneInterActionPlayStatusReq()
        req.ParseFromString(data)

        rsp = SceneInterActionPlayStatusRsp()
        rsp.status = StatusCode.StatusCode_OK
        if req.action_status.id not in [7001] or req.push_type in [
            0,
            1,
        ]:
            logger.info(
                "交互状态透传: id=%s push=%s", req.action_status.id, req.push_type
            )
            session.send(MsgId.SceneInterActionPlayStatusRsp, rsp, packet_id)
            _broadcast_interaction(session, req)
            return
        match req.action_status.id:
            case 7001:  # 放置家具
                if req.push_type == InterActionPushType.AddKeepingStatus:
                    furniture = db.get_furniture(
                        session.scene_id,
                        session.channel_id,
                        session.player_id,
                        req.action_status.value1,
                    )
                    if furniture:
                        db.del_furniture(
                            session.scene_id,
                            session.channel_id,
                            session.player_id,
                            req.action_status.value1,
                        )
                if req.push_type == InterActionPushType.RemovingStatus:
                    if req.action_status.value2:
                        tmp = FurnitureDetailsInfo()
                        tmp.furniture_id = req.action_status.value1
                        tmp.furniture_item_id = req.action_status.value2
                        tmp.pos.x = req.action_status.value3
                        tmp.pos.y = req.action_status.value4
                        tmp.pos.z = req.action_status.value5
                        tmp.rotation.y = req.action_status.value6
                        db.set_furniture(
                            session.scene_id,
                            session.channel_id,
                            session.player_id,
                            tmp.furniture_id,
                            tmp.SerializeToString(),
                        )

        session.send(MsgId.SceneInterActionPlayStatusRsp, rsp, packet_id)
        _broadcast_interaction(session, req)
