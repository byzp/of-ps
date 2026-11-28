from google.protobuf.message import DecodeError

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config

from proto.net_pb2 import (
    ItemDetail,
    PickupReq,
    PickupRsp,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils import achieve_track, item_mgr


@packet_handler(MsgId.PickupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        # 玩家经济锁必须先于会话掉落锁和 DB 事务, 与物品使用/宝箱领取一致。
        with (
            achieve_track.batch(session),
            item_mgr.player_lock(session.player_id),
            session.drop_lock,
        ):
            self._pickup(session, data, packet_id)

    def _pickup(self, session, data, packet_id):
        req = PickupReq()
        req.ParseFromString(data)
        rsp = PickupRsp()
        if req.drop_item_index == 0 or req.pick_index < -1:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.PickupRsp, rsp, packet_id)
            return

        remaining = session.drop_items.get(req.drop_item_index)
        if not remaining:
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.PickupRsp, rsp, packet_id)
            return
        if req.pick_index == -1:
            slots = list(range(len(remaining)))
        elif 1 <= req.pick_index <= len(remaining):
            slots = [req.pick_index - 1]
        else:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.PickupRsp, rsp, packet_id)
            return

        # 先完整解析并验证, 再写去重记录或物品。
        picks = []
        try:
            for slot in slots:
                item = ItemDetail()
                item.ParseFromString(remaining[slot])
                item_mgr.validate_pickup_item(item)
                picks.append((slot, item))
            instances = sum(item_mgr.needs_temp_pack(item) for _, item in picks)
            if len(session.temp_pack) + instances > Config.TEMP_PACK_MAX:
                rsp.status = StatusCode.StatusCode_Temp_Pack_Is_Full
                session.send(MsgId.PickupRsp, rsp, packet_id)
                return
        except (DecodeError, item_mgr.EconomyConfigError, TypeError, ValueError):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.PickupRsp, rsp, packet_id)
            return

        pack = PackNotice(status=StatusCode.StatusCode_OK)
        staged_temp_pack = []
        consumed_slots = []
        with item_mgr.deferred_notifications(), db.transaction():
            fresh = []
            for slot, item in picks:
                claim_key = f"{req.drop_item_index}:{slot}"
                if db.try_claim(session.player_id, "drop_pickup", claim_key):
                    fresh.append((slot, item))
                elif req.pick_index != -1:
                    rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            if not fresh:
                rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            else:
                item_mgr.pickup_rewards(
                    session,
                    [item for _, item in fresh],
                    rsp.items,
                    pack,
                    staged_temp_pack=staged_temp_pack,
                )
                consumed_slots = [slot for slot, _ in fresh]
                rsp.status = StatusCode.StatusCode_OK

        if rsp.status != StatusCode.StatusCode_OK:
            session.send(MsgId.PickupRsp, rsp, packet_id)
            return

        # 会话标记只在 DB 提交后变化; 任一步保存失败都会保留掉落供重试。
        consumed = set(consumed_slots)
        remaining[:] = [
            blob for slot, blob in enumerate(remaining) if slot not in consumed
        ]
        if not remaining:
            session.drop_items.pop(req.drop_item_index, None)
        session.temp_pack.extend(staged_temp_pack)
        for _, item in fresh:
            achieve_track.report(session, "pickup", match=item.main_item.item_id)
        session.send(MsgId.PickupRsp, rsp, packet_id)
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
