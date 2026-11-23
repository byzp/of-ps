from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config

from proto.net_pb2 import AreaUnlockReq, AreaUnlockRsp, StatusCode, AreaData, PackNotice

import utils.db as db
from utils import achieve_track, item_mgr


@packet_handler(MsgId.AreaUnlockReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaUnlockReq()
        req.ParseFromString(data)

        rsp = AreaUnlockRsp()
        rsp.status = StatusCode.StatusCode_OK
        # 只有状态确为 Unlock 才算重复解锁; AreaClose 会先行建 Close 行
        area_b = db.get_area(session.player_id, session.scene_id, req.area_id)
        already = False
        level = 1
        if area_b:
            cur = AreaData()
            cur.ParseFromString(area_b)
            already = cur.area_state == AreaData.AreaState.Unlock
            level = cur.level if cur.level else 1
        if already:
            rsp.status = StatusCode.StatusCode_AREA_ALREADY_UNLOCK
        else:
            rsp.area.area_id = req.area_id
            rsp.area.area_state = AreaData.AreaState.Unlock
            rsp.area.level = level
            rewards = (
                Config.AREA_UNLOCK_REWARDS
                if session.scene_id != Config.TUTORIAL_SCENE_ID
                else ()
            )
            for item_id, count in rewards:
                reward = rsp.area.items.add()
                reward.item_id = item_id
                reward.num = count
            db.set_area(
                session.player_id,
                session.scene_id,
                req.area_id,
                rsp.area.SerializeToString(),
            )
            # 区域装置解锁对应隐藏成就 60000225(条件类型139)，
            # area_id=1001 同时命中主线“登录区域装置”条件类型43(param=1)。
            notice = PackNotice()
            notice.status = StatusCode.StatusCode_OK
            with achieve_track.batch(session):
                item_mgr.grant_items(
                    session.player_id, rewards, pack_notice=notice, session=session
                )
                achieve_track.report(
                    session,
                    "area_unlock",
                    area_param=1 if req.area_id == 1001 else None,
                )
                achieve_track.explore_collect(session)
                session.send(MsgId.AreaUnlockRsp, rsp, packet_id)
                if notice.items:
                    session.send(MsgId.PackNotice, notice, 0)
            return

        session.send(MsgId.AreaUnlockRsp, rsp, packet_id)
