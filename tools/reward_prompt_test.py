"""隔离数据库回归：物品首获提示与星云树任务通知，不连接实际服务。"""

import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config
from proto import net_pb2 as pb
from handlers.AbilityBadgeAchieveReward import Handler as BadgeReward
from handlers.AbilityBadgeList import Handler as BadgeList
from handlers.OpreateMails import Handler as MailReward
from handlers.TempPackSort import Handler as TempPackSort
from utils import achieve_track, db, item_mgr, res_loader
from utils.pb_create import make_item


class RewardPromptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="of-reward-prompts-")
        Config.DB_PATH = str(Path(cls.directory.name) / "player.db")
        Config.IN_MEMORY = False
        Config.SKIP_QUESTS = False
        res_loader.init()
        db.init()
        cls.next_id = 1000001

    @classmethod
    def tearDownClass(cls):
        db.exit()
        cls.directory.cleanup()

    def setUp(self):
        self.pid = type(self).next_id
        type(self).next_id += 1
        db.init_player(self.pid)
        self.packets = []
        self.session = SimpleNamespace(
            player_id=self.pid,
            scene_id=1,
            quests={},
            temp_pack=[],
            send=lambda mid, msg, seq: self.packets.append(
                type(msg).FromString(msg.SerializeToString())
            ),
        )

    def test_stackable_first_repeated_and_spent(self):
        for first in (True, False):
            pack = pb.PackNotice()
            rsp = pb.AbilityBadgeAchieveRewardRsp()
            detail = item_mgr.grant_items(
                self.pid, [(301, 1)], rsp_items=rsp.items, pack_notice=pack
            )[0]
            self.assertEqual(detail.main_item.is_new, first)
            self.assertEqual(rsp.items[0].main_item.is_new, first)
            self.assertEqual(pack.items[0].main_item.is_new, first)
            self.assertFalse(
                pb.ItemDetail.FromString(
                    db.get_item_detail(self.pid, 301)
                ).main_item.is_new
            )
        self.assertTrue(item_mgr.consume_items(self.pid, [(301, 2)]))
        self.assertFalse(item_mgr.grant_single_item(self.pid, 301).main_item.is_new)

    def test_same_reward_batch_only_first_is_new(self):
        rewards = item_mgr.grant_items(self.pid, [(301, 1), (301, 1)])
        self.assertEqual([r.main_item.is_new for r in rewards], [True, False])
        self.assertEqual(item_mgr.get_num(self.pid, 301), 2)

    def test_first_acquisition_history_survives_database_reopen(self):
        self.assertTrue(item_mgr.grant_single_item(self.pid, 301).main_item.is_new)
        db.exit()
        db.init()
        self.assertFalse(item_mgr.grant_single_item(self.pid, 301).main_item.is_new)

    def test_unchanged_progress_does_not_send_notices(self):
        aid = 50101010
        achieve_track._write(self.session, self.pid, aid, 1)
        self.packets.clear()
        achieve_track._write(self.session, self.pid, aid, 1)
        self.assertEqual(self.packets, [])

    def test_initial_inventory_and_updates_are_not_new(self):
        for raw in db.get_item_detail(self.pid):
            item = pb.ItemDetail.FromString(raw)
            self.assertFalse(item.main_item.is_new)
            self.assertTrue(db.has_claimed(self.pid, "got_ids", item.main_item.item_id))
        item = item_mgr.grant_single_item(self.pid, 10, 1)
        self.assertFalse(item.main_item.is_new)

    def test_instances_remain_known_after_deletion(self):
        first = item_mgr.grant_single_item(self.pid, 1402202)
        self.assertTrue(first.main_item.is_new)
        db.del_item_detail(self.pid, first.main_item.weapon.instance_id)
        second = item_mgr.grant_single_item(self.pid, 1402202)
        self.assertFalse(second.main_item.is_new)
        self.assertNotEqual(
            first.main_item.weapon.instance_id, second.main_item.weapon.instance_id
        )

    def test_pickup_and_temp_pack_sort(self):
        for item_id in (5012011, 1402202):
            for first in (True, False):
                rsp, pack = pb.PickupRsp(), pb.PackNotice()
                source = make_item(item_id, 1, self.pid)
                self.assertFalse(source.main_item.is_new)
                item_mgr.pickup_rewards(self.session, [source], rsp.items, pack)
                self.assertEqual(rsp.items[0].main_item.is_new, first)
                self.assertEqual(pack.items[0].main_item.is_new, first)
                self.assertFalse(
                    pb.ItemDetail.FromString(
                        self.session.temp_pack[-1][1]
                    ).main_item.is_new
                )
        TempPackSort().handle(self.session, pb.TempPackSortReq().SerializeToString(), 1)
        self.assertTrue(
            all(not i.is_new for i in self.packets[-1].temp_pack.item_infos)
        )

    def test_mail_instances_only_first_template_is_new(self):
        for index, first in enumerate((True, False), 100):
            mail = pb.MailBriefData(mail_id=index)
            mail.reward.add().CopyFrom(make_item(1402202, 1, self.pid))
            db.set_mail(self.pid, index, mail.SerializeToString())
            self.packets.clear()
            MailReward().handle(
                self.session,
                pb.OperateMailsReq(
                    mail_id=index, operate_type=pb.MailOperateType_CLAIM
                ).SerializeToString(),
                index,
            )
            response = next(
                p for p in self.packets if isinstance(p, pb.OperateMailsRsp)
            )
            self.assertEqual(response.claim_result[0].main_item.is_new, first)

    def test_character_defaults_and_duplicate_conversion(self):
        known = set(db.get_claimed(self.pid, "got_ids"))
        pack, character = pb.PackNotice(), pb.ItemDetail()
        self.assertFalse(item_mgr.grant_character(self.pid, 102001, character, pack))
        self.assertTrue(character.main_item.is_new)
        for item in pack.items:
            key = str(item.main_item.item_id)
            self.assertEqual(item.main_item.is_new, key not in known)
            known.add(key)
        first = item_mgr.grant_items(self.pid, [(102001, 1)])[0]
        second = item_mgr.grant_items(self.pid, [(102001, 1)])[0]
        self.assertEqual(first.main_item.item_id, second.main_item.item_id)
        self.assertTrue(first.main_item.is_new)
        self.assertFalse(second.main_item.is_new)

    def test_concurrent_grants_only_one_first_and_no_lost_count(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            items = list(
                executor.map(
                    lambda _: item_mgr.grant_single_item(self.pid, 301), range(16)
                )
            )
        self.assertEqual(sum(i.main_item.is_new for i in items), 1)
        self.assertEqual(item_mgr.get_num(self.pid, 301), 16)

    def test_claimed_star_tasks_do_not_repeat_completion(self):
        rows = res_loader.res["Achieve"]["achieve"]["datas"]
        ids = {
            info["achieve_condition_i_d"]
            for group in res_loader.res["MoonStone"]["stone_reward_quest_data"]["datas"]
            for info in group["stone_reward_quest_data_group_info"]
        }
        for ctype, event, args in (
            (106, "kill", {"match": 1001, "monster_tag": 0}),
            (3, "treasure_box", {}),
        ):
            tasks = sorted(
                (
                    r
                    for r in rows
                    if r.get("i_d") in ids
                    and r.get("new_achieve_condition") == ctype
                    and r.get("param") == (1,)
                ),
                key=lambda r: r["count_param"],
            )
            task = tasks[0]
            aid, target = task["i_d"], task["count_param"]
            self.packets.clear()
            for _ in range(target):
                achieve_track.report(self.session, event, **args)
            first_notices = [
                a
                for p in self.packets
                if isinstance(p, pb.AchieveNotice)
                for a in p.achieves
                if a.achieve_id == aid and a.count == target
            ]
            self.assertEqual(len(first_notices), 1)
            self.packets.clear()
            BadgeReward().handle(
                self.session,
                pb.AbilityBadgeAchieveRewardReq(achieve_ids=[aid]).SerializeToString(),
                1,
            )
            response = next(
                p
                for p in self.packets
                if isinstance(p, pb.AbilityBadgeAchieveRewardRsp)
            )
            self.assertEqual(response.status, pb.StatusCode_OK)
            self.assertEqual(response.items[0].main_item.is_new, ctype == 106)
            self.packets.clear()
            for _ in range(3):
                achieve_track.report(self.session, event, **args)
            BadgeList().handle(
                self.session, pb.AbilityBadgeListReq(scene_id=1).SerializeToString(), 2
            )
            for message in self.packets:
                if isinstance(message, pb.AchieveNotice):
                    self.assertNotIn(aid, [a.achieve_id for a in message.achieves])
                if isinstance(message, pb.AchieveFinishNotice):
                    self.assertNotEqual(message.finish_info.achieve_id, aid)
            self.assertEqual(
                achieve_track.progress(self.pid, tasks[1]["i_d"]), target + 3
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
