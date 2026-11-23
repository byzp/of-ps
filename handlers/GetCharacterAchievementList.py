from proto.net_pb2 import Character as PbChar

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    Achieve,
    GetCharacterAchievementListReq,
    GetCharacterAchievementListRsp,
    StatusCode,
)
import utils.db as db


@packet_handler(MsgId.GetCharacterAchievementListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCharacterAchievementListReq()
        req.ParseFromString(data)
        chr_id = req.character_id

        rsp = GetCharacterAchievementListRsp()
        rsp.status = StatusCode.StatusCode_OK
        for entry in db.get_character_achievement_lst(session.player_id, chr_id) or []:
            a_id = entry.get("achieve_i_d") if isinstance(entry, dict) else None
            if not a_id:
                continue
            achieve_b = db.get_achieve(session.player_id, a_id)
            if not achieve_b:
                continue
            tmp = Achieve()
            tmp.ParseFromString(achieve_b)
            if tmp.count <= 0:
                continue
            rsp.character_achievement_lst.add().CopyFrom(tmp)
        rsp.character_id = chr_id

        # 领取状态与付费档解锁(Character blob 为准)
        chars = db.get_characters(session.player_id, chr_id)
        if chars:

            c = PbChar()
            c.ParseFromString(chars[0])
            rsp.rewarded_id_lst.extend(c.reward_index_lst)
            rsp.has_rewarded_ids.extend(c.reward_index_lst)
            rsp.is_unlocked_payment = c.is_unlock_payment
        session.send(MsgId.GetCharacterAchievementListRsp, rsp, packet_id)  # 1479,1480
