import contextlib
import json
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from network.msg_id import MsgId
from proto.net_pb2 import (
    BossRushEnterStageReq,
    BossRushInfo,
    BossRushLeaveStageReq,
    BossRushStartBattleReq,
    BossRushStartChallengeReq,
    Character,
    StatusCode,
)
from server import boss_rush
import handlers.BossRushEnterStage as enter
import handlers.BossRushLeaveStage as leave
import handlers.BossRushStartBattle as start_battle
import handlers.BossRushStartChallenge as start_challenge
import utils.db as db
import utils.res_loader as res_loader


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class BossRushTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        res_loader.init()

    def setUp(self):
        self.session = FakeSession()
        self.infos = {}
        self.kv = {}
        # 活动赛季在真实时间线上已经结束；用例只验证服务端逻辑，固定为开启，
        # 并把赛季窗口平移到当前时间，避免结算时限依赖真实日历。
        season_active = patch.object(boss_rush, 'season_active', return_value=True)
        season_active.start()
        self.addCleanup(season_active.stop)
        season_row = boss_rush.season
        now = datetime.now()

        def active_window(season_id):
            row = season_row(season_id)
            if row is None:
                return None
            return dict(
                row,
                start_time=(now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'),
                end_time=(now + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'),
            )

        season_window = patch.object(boss_rush, 'season', side_effect=active_window)
        season_window.start()
        self.addCleanup(season_window.stop)

    def patch_db(self):
        return [
            patch.object(db, 'get_boss_rush_info', side_effect=lambda player, season: self.infos.get(season)),
            patch.object(db, 'set_boss_rush_info', side_effect=lambda player, season, blob: self.infos.__setitem__(season, blob)),
            patch.object(db, 'get_kv', side_effect=lambda player, ns, key: self.kv.get((ns, key))),
            patch.object(db, 'set_kv', side_effect=lambda player, ns, key, value: self.kv.__setitem__((ns, key), value)),
            patch.object(db, 'del_kv', side_effect=lambda player, ns, key: self.kv.pop((ns, key), None)),
            patch.object(db, 'get_players_info', return_value=[80]),
            patch.object(db, 'transaction', side_effect=contextlib.nullcontext),
        ]

    def test_info_initializes_all_configured_stages(self):
        season = boss_rush.season(1001)
        info = boss_rush.new_info(season)
        self.assertEqual([stage.stage_index for stage in info.stage_infos], [0, 1, 2])
        self.assertGreater(info.start_time, 0)

    def test_battle_info_contains_monster_hp(self):
        battle = boss_rush.battle_info(boss_rush.season(1001), 0)
        self.assertIsNotNone(battle)
        self.assertEqual(battle.stage_index, 0)
        self.assertEqual(battle.monsters[0].monster_id, 1306)
        self.assertGreater(battle.monsters[0].remain_hp, 0)

    def test_start_challenge_rejects_invalid_stage(self):
        with self.patch_db()[0]:
            start_challenge.Handler().handle(self.session, BossRushStartChallengeReq(season_id=1001, stage_index=99).SerializeToString(), 1)
        self.assertEqual(self.session.sent[0][1].status, StatusCode.StatusCode_BAD_REQ)

    def test_full_stage_flow_settles_once(self):
        patches = self.patch_db()
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        character = Character(character_id=101001)
        with patch.object(db, 'get_characters', return_value=[character.SerializeToString()]):
            start_challenge.Handler().handle(self.session, BossRushStartChallengeReq(season_id=1001, stage_index=0).SerializeToString(), 1)
            self.assertEqual(self.session.sent[-1][1].status, StatusCode.StatusCode_OK)
            enter.Handler().handle(self.session, BossRushEnterStageReq(season_id=1001, characters=[101001]).SerializeToString(), 2)
            self.assertEqual(self.session.sent[-1][1].status, StatusCode.StatusCode_OK)
            self.assertGreater(self.session.sent[-1][1].battle_info.monsters[0].remain_hp, 0)
            start_battle.Handler().handle(self.session, BossRushStartBattleReq(season_id=1001).SerializeToString(), 3)
            self.assertEqual(self.session.sent[-1][1].status, StatusCode.StatusCode_OK)
        key = ('boss_rush', '1001:battle_start')
        self.kv[key] = int(time.time() * 1000) - 1000
        run_key = ('boss_rush', '1001:run')
        run = json.loads(self.kv[run_key])
        run['battle_start_ms'] = int(time.time() * 1000) - 1000
        self.kv[run_key] = json.dumps(run, sort_keys=True).encode('utf-8')
        max_hp = boss_rush.stage_config(boss_rush.season(1001), 0)['max_h_p']
        report = boss_rush.battle_info(boss_rush.season(1001), 0)
        for monster in report.monsters:
            monster.remain_hp = 0
        leave.Handler().handle(
            self.session,
            BossRushLeaveStageReq(season_id=1001, total_damage_hp=max_hp, win=True, battle_info=report).SerializeToString(),
            4,
        )
        rsp = self.session.sent[-1][1]
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        self.assertEqual(rsp.stage_best_score, max_hp)
        self.assertEqual(rsp.best_total_score, max_hp)
        self.assertNotIn(key, self.kv)
        info = BossRushInfo()
        info.ParseFromString(self.infos[1001])
        self.assertEqual(info.current_stage_index, -1)
        self.assertTrue(info.stage_infos[0].is_passed)
        leave.Handler().handle(self.session, BossRushLeaveStageReq(season_id=1001, total_damage_hp=max_hp, win=True).SerializeToString(), 5)
        self.assertEqual(self.session.sent[-1][1].status, StatusCode.StatusCode_BAD_REQ)

    def test_start_battle_requires_entered_team(self):
        patches = self.patch_db()
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        info = boss_rush.new_info(boss_rush.season(1001))
        info.current_stage_index = 0
        info.challenge_end_time = int(time.time()) + 3600
        self.infos[1001] = info.SerializeToString()
        start_battle.Handler().handle(self.session, BossRushStartBattleReq(season_id=1001).SerializeToString(), 1)
        self.assertEqual(self.session.sent[0][1].status, StatusCode.StatusCode_BAD_REQ)


if __name__ == '__main__':
    unittest.main(verbosity=2)
