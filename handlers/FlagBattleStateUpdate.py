from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config

from proto.net_pb2 import (
    FlagBattleStateUpdateReq,
    FlagBattleStateUpdateRsp,
    FlagUnLockRemoveNotice,
    StatusCode,
    BattleState,
    EMissionType,
    PackNotice,
)

import utils.db as db
from utils import achieve_track, item_mgr
from utils.reward_resolver import resolve_drop
from utils.res_loader import res
from utils import flag_state, battle_rewards

"""
# 旗帜战斗状态更新 1325 1326(官方抓包 pack/pack0 实锤)
普通战斗 Start req → Rsp 仅 battle_data{battle_id}(state/type 为默认0)。
其他战斗类型必须回传 mission_type，例如主线160120是采集战斗6；
省略type会让客户端按普通战斗处理，无法启动对应玩法。
Fail req → Rsp battle_data{battle_id, state:Fail}(旗帜保留)。
Finish req → 首通时服务器连发: FlagUnLockRemoveNotice(1582, 反查
  Flag.json flag_group_info.relation_i_d 得 flag_id) →
  Rsp battle_data{battle_id, state:Finish} +
  dynamic_treasure_box_base_info{box_id:300000, index:K}(K 与玩法/遭遇
  战宝箱共用 kv dyn_box 递增序号, 登录实测 1,2,3,4 连续), 奖励装在箱内
  由 TreasureBoxOpen(DYNAMIC) 领取; 重复通关不再发箱/不再推 1582。
官方回包不带 type/finish_times(仅登录 SceneDataNotice 回放使用, 本仓
proto 无该回放字段); max_quality 配置来源未定位, 不伪造。
"""


def _flag_ids_of_battle(battle_id):
    out = []
    for row in res.get("Flag", {}).get("flag", {}).get("datas", ()):
        for g in row.get("flag_group_info", ()):
            if g.get("relation_i_d") == battle_id:
                out.append(row.get("i_d"))
                break
    return out


@packet_handler(MsgId.FlagBattleStateUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FlagBattleStateUpdateReq()
        req.ParseFromString(data)

        rsp = FlagBattleStateUpdateRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.battle_data.battle_id = req.battle_id
        rsp.battle_data.type = req.mission_type
        if req.mission_type == EMissionType.EMissionType_ScenicSpot:
            # 景点仅发一个无Finish的请求；服务端直接完成播放并发放照片。
            scenic = next(
                (
                    row
                    for row in res["Scenic"]["scenic"]["datas"]
                    if row.get("i_d") == req.battle_id
                ),
                None,
            )
            if scenic is None:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.FlagBattleStateUpdateRsp, rsp, packet_id)
                return
            rsp.battle_data.state = BattleState.Finish
            rsp.battle_data.voice_id = Config.SCENIC_VOICE_IDS.get(
                req.battle_id, scenic.get("guide_voice", 0)
            )
            first = not db.get_kv(
                session.player_id, "flag_battle", f"b:{req.battle_id}", 0
            )
            pack = PackNotice(status=StatusCode.StatusCode_OK)
            with achieve_track.batch(session):
                if first:
                    db.set_kv(session.player_id, "flag_battle", f"b:{req.battle_id}", 1)
                    level, world_level = db.get_players_info(
                        session.player_id, "level,world_level"
                    )
                    rewards = resolve_drop(
                        scenic.get("first_reward_i_d"), world_level, level
                    )
                    item_mgr.grant_items(
                        session.player_id, rewards, pack_notice=pack, session=session
                    )
                    for flag_id in _flag_ids_of_battle(req.battle_id):
                        achieve_track.scenic(session, flag_id)
                    achieve_track.explore_collect(session)
                    achieve_track.add(session, 4, match=req.battle_id)
                session.send(MsgId.FlagBattleStateUpdateRsp, rsp, packet_id)
                if pack.items:
                    session.send(MsgId.PackNotice, pack, 0)
            return

        if req.battle_state == BattleState.Finish:
            rsp.battle_data.state = BattleState.Finish
            first = not db.get_kv(
                session.player_id, "flag_battle", f"b:{req.battle_id}", 0
            )
            if first:
                battle_rewards.grant_character_exp(session, "flag", req.battle_id)
                db.set_kv(session.player_id, "flag_battle", f"b:{req.battle_id}", 1)
                flag_ids = _flag_ids_of_battle(req.battle_id)
                if flag_ids:
                    flag_state.remove_scene_flags(session.player_id, flag_ids)
                    rm = FlagUnLockRemoveNotice()
                    rm.status = StatusCode.StatusCode_OK
                    for fid in flag_ids:
                        rm.flag_ids.append(fid)
                    session.send(MsgId.FlagUnLockRemoveNotice, rm, 0)
                # 首通掉落动态宝箱(TreasureBox.encounter_treasure_box 300000)
                datas = (
                    res.get("TreasureBox", {})
                    .get("encounter_treasure_box", {})
                    .get("datas", ())
                )
                box = next(iter(datas), None) if datas else None
                if box and box.get("i_d"):
                    idx = db.incr_kv(session.player_id, "dyn_box", "seq")
                    db.set_kv(session.player_id, "dyn_box", idx, box["i_d"])
                    rsp.dynamic_treasure_box_base_info.box_id = box["i_d"]
                    rsp.dynamic_treasure_box_base_info.index = idx
        elif req.battle_state == BattleState.Fail:
            rsp.battle_data.state = BattleState.Fail

        session.send(MsgId.FlagBattleStateUpdateRsp, rsp, packet_id)

        if req.battle_state == BattleState.Finish:
            with achieve_track.batch(session):
                if first:
                    achieve_track.report(session, "battle_finish")
                    # 指定战斗/风车教学条件同样落到通用成就，禁止只改任务 blob。
                    achieve_track.add(session, 4, match=req.battle_id)
