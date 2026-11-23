from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    CharacterLevelUpReq,
    CharacterLevelUpRsp,
    StatusCode,
    PackNotice,
    Character,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils import achieve_track

"""
# 角色升级 1039 1040(官方抓包 pack0 实锤: 批量喝能量饮料连升多级)
经验源 Item.json tag19 道具的 relate_i_d(190=1000/191=5000/192=20000,
与官方 req nums 4/2/5 升 18 级的曲线和值吻合); 升级曲线为
Character.json level.datas[i_d=1].level_info(全部角色 growth_level_i_d=1),
条目按 **character_id 字段=等级序号** 给出升到下一级所需 exp(99 段)。
本仓数据无 exp_to_coin 列 —— 原金币折算为参考库漂移字段, 已移除。
包序: Rsp → 1400(饮料消耗回显, 官方每次升级必有) → 帧尾成就/任务。
先校验角色存在, 再原子扣道具(原实现角色不存在时饮料已扣)。
"""


def _exp_per_item(item_id):
    for e in res["Item"]["item"]["datas"]:
        if e.get("i_d") == item_id:
            return int(e.get("relate_i_d", 0) or 0)
    return 0


def _level_curve():
    return {
        e["character_id"]: e["exp"]
        for e in res["Character"]["level"]["datas"][0]["level_info"]
    }


@packet_handler(MsgId.CharacterLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterLevelUpReq()
        req.ParseFromString(data)

        rsp = CharacterLevelUpRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 角色必须先存在(不满足则零消耗零变更)
        character_data_list = db.get_characters(session.player_id, req.char_id)
        if not character_data_list:
            rsp.status = StatusCode.StatusCode_CharNotExist
            session.send(MsgId.CharacterLevelUpRsp, rsp, packet_id)  # 1039,1040
            return

        nums = list(req.nums) + [0] * (3 - len(req.nums))
        costs = []
        total_exp = 0
        for idx, item_id in enumerate(Config.CHARACTER_LEVEL_UP_ENERGY_ITEMS):
            q = int(nums[idx] or 0)
            if q > 0:
                costs.append((item_id, q))
                total_exp += q * _exp_per_item(item_id)

        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK
        with achieve_track.batch(session):
            if costs and not item_mgr.consume_items(
                session.player_id,
                costs,
                pack_notice=notice,
                session=session,
            ):
                # 任一饮料不足: 整单不扣不发
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.CharacterLevelUpRsp, rsp, packet_id)
                return
            achieve_track.report(
                session, "energy_drink", amount=sum(int(n or 0) for n in nums)
            )

            character = Character()
            character.ParseFromString(character_data_list[0])
            curve = _level_curve()
            new_level = character.level
            new_exp = character.exp + total_exp
            while new_level < character.max_level:
                need = curve.get(new_level)
                if need is None or new_exp < need:
                    break
                new_exp -= need
                new_level += 1
            if new_level >= character.max_level:
                new_exp = 0

            character.level = new_level
            character.exp = new_exp
            db.set_character(
                session.player_id, req.char_id, character.SerializeToString()
            )
            # 成就: 分角色等级35 / N个角色达到X级79 /
            # 队长等级36(队长角色升级时判定)。类型35按角色 id 参数匹配。
            achieve_track.report(
                session,
                "character_level",
                match=req.char_id,
                level=new_level,
            )
            achieve_track.character_level_count(session)
            if achieve_track.captain_id(session.player_id) == req.char_id:
                achieve_track.captain_level(session, new_level)

            rsp.char_id = req.char_id
            rsp.level = new_level
            rsp.exp = new_exp
            session.send(MsgId.CharacterLevelUpRsp, rsp, packet_id)  # 1039,1040
            if len(notice.items):
                session.send(MsgId.PackNotice, notice, 0)  # 1400
