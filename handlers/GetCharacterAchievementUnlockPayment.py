from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GetCharacterAchievementUnlockPaymentReq,
    GetCharacterAchievementUnlockPaymentRsp,
    StatusCode,
    Character,
)

import utils.db as db

"""
# 付费解锁角色成就 1483 1484
解锁状态持久化在 Character.is_unlock_payment(characters 表 blob, 重启不丢,
GetCharacterAchievementAward 领付费档时校验该位)。
注: 解锁费用不扣任何道具, update_item 留空 —— 已查 Character.json 各分表与
GlobalConfig 均无对应道具/货币配置, new_reward_price_type 仅是档位标记,
该解锁在官服走平台内购(法币), 私服无支付渠道, 故直接置解锁成功
"""


@packet_handler(MsgId.GetCharacterAchievementUnlockPaymentReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCharacterAchievementUnlockPaymentReq()
        req.ParseFromString(data)

        rsp = GetCharacterAchievementUnlockPaymentRsp()
        rsp.character_id = req.character_id

        characters = db.get_characters(session.player_id, req.character_id)
        if not characters:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GetCharacterAchievementUnlockPaymentRsp, rsp, packet_id)
            return

        chr = Character()
        chr.ParseFromString(characters[0])
        if not chr.is_unlock_payment:
            chr.is_unlock_payment = True
            db.set_character(
                session.player_id, req.character_id, chr.SerializeToString()
            )
        rsp.update_item.main_item.character.CopyFrom(chr)
        rsp.update_item.main_item.item_id = req.character_id

        rsp.status = StatusCode.StatusCode_OK
        rsp.is_unlock = True
        session.send(
            MsgId.GetCharacterAchievementUnlockPaymentRsp, rsp, packet_id
        )  # 1483,1484
