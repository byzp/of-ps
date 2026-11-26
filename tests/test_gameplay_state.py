import contextlib
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import (
    Character,
    CharacterEquipUpdateReq,
    CharacterSkill,
    CharacterSkillLevelUpReq,
    ClaimQuestRewardReq,
    DungeonFinishReq,
    EBagItemTag,
    FishingReq,
    GatherReq,
    ItemDetail,
    PlaceFurnitureReq,
    StatusCode,
)
import handlers.CharacterEquipUpdate as equip
import handlers.CharacterSkillLevelUp as skill_upgrade
import handlers.ClaimQuestReward as claim
import handlers.DungeonFinish as dungeon_finish
import handlers.Fishing as fishing
import handlers.Gather as gather
import handlers.PlaceFurniture as place
import utils.db as db
import utils.res_loader as res_loader
from utils import item_mgr


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.player_name = 'Synthetic'
        self.scene_id = 9999
        self.channel_id = player_id
        self.running = True
        self.fishing = False
        self.fishing_token = ''
        self.dungeon = [0, 0, 0, -1]
        self.dungeon_token = ''
        self.quests = {}
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class GameplayStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        res_loader.init()

    def test_gather_point_has_cooldown(self):
        session = FakeSession()
        store = {}
        request = GatherReq()
        request.gather_item.index = 3
        request.gather_item.reward = res_loader.res['Gather']['gather_reward']['datas'][0]['i_d']
        with patch.object(db, 'get_kv', side_effect=lambda player, ns, key, default=0: store.get((ns, key), default)), \
             patch.object(db, 'set_kv', side_effect=lambda player, ns, key, value: store.__setitem__((ns, key), value)), \
             patch.object(db, 'transaction', side_effect=contextlib.nullcontext), \
             patch.object(item_mgr, 'player_lock', return_value=threading.Lock()), \
             patch.object(item_mgr, 'grant_items'):
            gather.Handler().handle(session, request.SerializeToString(), 1)
            self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_OK)
            gather.Handler().handle(session, request.SerializeToString(), 2)
            self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_GATHER_LIMIT)

    def test_fishing_without_energy_does_not_start_timer(self):
        session = FakeSession()
        with patch.object(fishing, '_fishing_level', return_value=1), \
             patch.object(fishing, '_cast_cost', return_value=(11, 1)), \
             patch.object(fishing.item_mgr, 'consume_items', return_value=False), \
             patch.object(fishing.threading, 'Timer') as timer:
            fishing.Handler().handle(session, FishingReq().SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_EnergyNotEnough)
        self.assertFalse(session.fishing)
        timer.assert_not_called()

    def test_duplicate_fishing_is_rejected_and_cancel_clears_state(self):
        session = FakeSession()
        timer = Mock()
        with patch.object(fishing, '_fishing_level', return_value=1), \
             patch.object(fishing, '_cast_cost', return_value=(11, 1)), \
             patch.object(fishing.item_mgr, 'consume_items', return_value=True), \
             patch.object(fishing.item_mgr, 'grant_items'), \
             patch.object(fishing.random, 'randint', return_value=3), \
             patch.object(fishing.random, 'random', return_value=1), \
             patch.object(fishing.threading, 'Timer', return_value=timer):
            fishing.Handler().handle(session, FishingReq().SerializeToString(), 1)
            self.assertTrue(session.fishing)
            fishing.Handler().handle(session, FishingReq().SerializeToString(), 2)
            self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_BAD_REQ)
            fishing.Handler().handle(session, FishingReq(is_cancel=True).SerializeToString(), 3)
            self.assertFalse(session.fishing)
            self.assertEqual(session.fishing_token, '')

    def test_garden_capacity_blocks_placement(self):
        session = FakeSession()
        item = ItemDetail()
        item.main_item.item_id = 5040001
        item.main_item.item_tag = EBagItemTag.EBagItemTag_Furniture
        item.main_item.base_item.num = 1
        request = PlaceFurnitureReq(furniture_id=1, furniture_item_id=5040001)
        with patch.object(db, 'get_furniture', return_value=None), \
             patch.object(db, 'get_item_detail', return_value=item.SerializeToString()), \
             patch.object(place.garden_state, 'adjust_furniture_count', return_value=(10, 10)), \
             patch.object(place.item_mgr, 'consume_items') as consume:
            place.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_FAIL)
        consume.assert_not_called()

    def test_dungeon_finish_is_idempotent_per_run(self):
        session = FakeSession()
        session.dungeon = [1001, 0, 0, -1]
        session.dungeon_token = 'run-token'
        with patch.object(db, 'try_claim', return_value=False), \
             patch.object(db, 'get_dungeon') as load:
            dungeon_finish.Handler().handle(session, DungeonFinishReq().SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_REPEAT_GET_REWARD)
        load.assert_not_called()

    def test_skill_upgrade_updates_character_blob(self):
        session = FakeSession()
        character = Character(character_id=101001)
        character.character_skill_list.add(skill_id=1010700, skill_level=1)
        stored = []
        with patch.object(db, 'get_characters', return_value=[character.SerializeToString()]), \
             patch.object(db, 'set_character', side_effect=lambda player, char, blob: stored.append(blob)), \
             patch.object(db, 'transaction', side_effect=contextlib.nullcontext), \
             patch.object(item_mgr, 'player_lock', return_value=threading.RLock()), \
             patch.object(item_mgr, 'consume_items', return_value=True), \
             patch.object(skill_upgrade.achieve_track, 'report'):
            skill_upgrade.Handler().handle(session, CharacterSkillLevelUpReq(char_id=101001, skill_id=1010700).SerializeToString(), 1)
        updated = Character()
        updated.ParseFromString(stored[0])
        self.assertEqual(updated.character_skill_list[0].skill_level, 2)
        self.assertEqual(session.sent[-1][1].skill.skill_level, 2)

    def test_equipment_rejects_nonexistent_instance(self):
        session = FakeSession()
        character = Character(character_id=101001)
        request = CharacterEquipUpdateReq(char_id=101001)
        request.equipment_preset.preset_index = 0
        request.equipment_preset.weapon = 999999
        with patch.object(db, 'get_characters', return_value=[character.SerializeToString()]), \
             patch.object(db, 'get_item_detail', return_value=[]), \
             patch.object(db, 'transaction', side_effect=contextlib.nullcontext), \
             patch.object(item_mgr, 'player_lock', return_value=threading.RLock()), \
             patch.object(db, 'set_character') as save:
            equip.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_BAD_REQ)
        save.assert_not_called()

    def test_unaccepted_quest_cannot_be_claimed(self):
        session = FakeSession()
        story_ids = {row['i_d'] for row in res_loader.res['Story']['story']['datas']}
        quest_id = next(row['i_d'] for row in res_loader.res['Quest']['quest']['datas'] if row['i_d'] not in story_ids)
        with patch.object(db, 'get_players_info', return_value=[1]), \
             patch.object(db, 'get_quest', return_value=None), \
             patch.object(claim.item_mgr, 'grant_items') as grant:
            claim.Handler().handle(session, ClaimQuestRewardReq(quest_id=quest_id).SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_BAD_REQ)
        grant.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
