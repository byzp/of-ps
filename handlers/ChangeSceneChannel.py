from utils import achieve_track as _at

from handlers.GardenPlaceCharacter import replay_placements

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from network.remote_link import sync_subscriptions
from config import Config

from proto.net_pb2 import (
    ChangeSceneChannelReq,
    ChangeSceneChannelRsp,
    SceneDataNotice,
    ServerSceneSyncDataNotice,
    StatusCode,
    PackNotice,
    SceneActionType,
    ChatMsgRecordInitNotice,
    SceneWeatherChangeNotice,
)

import server.scene_data as scene_data
import server.notice_sync as notice_sync
from server import shared_projection
import utils.db as db
from utils.res_loader import res
from utils import refresh
from utils import mail_rewards
from utils.pb_create import make_SceneDataNotice
from utils import achieve_track
from utils import weather


@packet_handler(MsgId.ChangeSceneChannelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeSceneChannelReq()
        req.ParseFromString(data)

        # 场景须在 Scene.scene 配置内(含花园 9999)
        _scenes = {
            sc["i_d"]
            for sc in res.get("Scene", {}).get("scene", {}).get("datas", [])
            if isinstance(sc, dict)
        }
        if _scenes and req.scene_id not in _scenes:
            rsp = ChangeSceneChannelRsp()
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ChangeSceneChannelRsp, rsp, packet_id)
            return

        # 定向加入他人频道: 先验目标可达性, 失败回 BAD_REQ + 场景/频道
        # 回显, 且不得产生离开广播
        target_sid = None
        if req.target_player_label:
            for other in scene_data.get_session():
                if other.player_id == req.target_player_label:
                    target_sid = other
                    break
            if target_sid is None:
                rsp = ChangeSceneChannelRsp()
                rsp.status = StatusCode.StatusCode_BAD_REQ
                rsp.scene_id = req.scene_id
                rsp.channel_id = req.channel_label or session.channel_id
                rsp.channel_label = req.channel_label
                session.send(MsgId.ChangeSceneChannelRsp, rsp, packet_id)
                return

        # 向其他玩家广播离开事件
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = SceneActionType.SceneActionType_LEAVE
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)

        if req.scene_id == 9999:
            mail_rewards.settle_temp_pack(session)
        if req.scene_id != session.scene_id:
            mail_rewards.recover_drops(session)
        if (
            session.scene_id == Config.TUTORIAL_SCENE_ID
            and req.scene_id != session.scene_id
        ):
            db.del_kv(session.player_id, "profile", "tutorial_pending")
        with shared_projection.store.locked():
            scene_data.remove_recorder(
                session.scene_id, session.channel_id, session.player_id
            )
            session.scene_id = req.scene_id
            if target_sid is not None:
                session.channel_id = target_sid.channel_id
            else:
                session.channel_id = req.channel_label or session.player_id
            shared_projection.store.move(
                session.player_id, session.scene_id, session.channel_id
            )
        scene_data.save_session_location(session, force=True)

        # 主线任务条件: 进入指定空间

        _at.report(session, "scene_enter", match=req.scene_id)

        rsp = ChangeSceneChannelRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.scene_id = req.scene_id
        rsp.channel_id = session.channel_id

        # 成就: 切换频道
        achieve_track.report(session, "channel_switch")
        session.send(MsgId.ChangeSceneChannelRsp, rsp, packet_id)

        # 更新场景
        rsp = SceneDataNotice()
        rsp.CopyFrom(make_SceneDataNotice(session))
        session.send(MsgId.SceneDataNotice, rsp, 0)
        weather_notice = SceneWeatherChangeNotice(
            status=StatusCode.StatusCode_OK,
            weather_type=weather.weather_at(int(notice_sync.game_time_seconds // 3600)),
        )
        session.send(MsgId.SceneWeatherChangeNotice, weather_notice, 0)

        for i in db.get_chat_history(session.player_id):
            if not i["msg"]:
                continue
            rsp2 = ChatMsgRecordInitNotice()
            rsp2.status = StatusCode.StatusCode_OK
            rsp2.type = i["type"]
            for m in i["msg"]:
                t1 = rsp2.msg.add()
                for k, v in m.items():
                    setattr(t1, k, v)
            session.send(MsgId.ChatMsgRecordInitNotice, rsp2, packet_id)

        # 回花园时将临时背包物品更新到仓库
        if req.scene_id == 9999:
            # 重放花园已放置角色(客户端恢复椅子角色显示)

            replay_placements(session)

        # 广播加入消息
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = SceneActionType.SceneActionType_ENTER
        sd.player.CopyFrom(session.scene_player)
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)
        sync_subscriptions()
