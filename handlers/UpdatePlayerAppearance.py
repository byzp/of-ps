from server import scene_data as _sd

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    ServerSceneSyncDataNotice,
    SceneActionType,
    UpdatePlayerAppearanceReq,
    UpdatePlayerAppearanceRsp,
    StatusCode,
)
import utils.db as db
from utils.res_loader import res
import utils.pb_create as pb_create


@packet_handler(MsgId.UpdatePlayerAppearanceReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdatePlayerAppearanceReq()
        req.ParseFromString(data)

        rsp = UpdatePlayerAppearanceRsp()

        # 挂件须在 Pendant.pendant 配置内(0=无)
        _pends = {
            p["i_d"] for p in res.get("Pendant", {}).get("pendant", {}).get("datas", [])
        }
        if (
            req.HasField("appearance")
            and req.appearance.pendant
            and _pends
            and (req.appearance.pendant not in _pends)
        ):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.UpdatePlayerAppearanceRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK

        rsp.appearance.avatar_frame = req.appearance.avatar_frame
        rsp.appearance.pendant = req.appearance.pendant

        db.set_players_info(
            session.player_id, "avatar_frame", req.appearance.avatar_frame
        )
        db.set_players_info(session.player_id, "pendant", req.appearance.pendant)

        session.send(
            MsgId.UpdatePlayerAppearanceRsp, rsp, packet_id
        )  # 更换头像框 挂件 2631 2632

        pb_create.make_ScenePlayer(session)
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        entry = notice.data.add()
        entry.player_id = session.player_id
        sd = entry.server_data.add()
        sd.action_type = SceneActionType.SceneActionType_UPDATE_APPEARANCE
        sd.player.CopyFrom(session.scene_player)

        for s in _sd.get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.ServerSceneSyncDataNotice, notice, 0)
