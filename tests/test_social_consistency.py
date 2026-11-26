import concurrent.futures
import contextlib
import pickle
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
import utils.db as db
import utils.res_loader as res_loader
from network.msg_id import MsgId
from proto.net_pb2 import (
    ChatChannelType,
    FriendAddReq,
    FriendBlackReq,
    FriendDelReq,
    FriendHandleReq,
    IntervalJoinReq,
    PrivateChatMsgRecordReq,
    SendChatMsgReq,
    StatusCode,
)
from server import social
import handlers.FriendAdd as friend_add
import handlers.FriendBlack as friend_black
import handlers.FriendDel as friend_del
import handlers.FriendHandle as friend_handle
import handlers.IntervalJoin as interval_join
import handlers.PrivateChatMsgRecord as private_record
import handlers.SendChatMsg as send_chat
import utils.garden_state as garden_state


class FakeSession:
    def __init__(self, player_id):
        self.player_id = player_id
        self.player_name = f"player-{player_id}"
        self.avatar_id = 41100 + player_id
        self.badge_id = 5000 + player_id
        self.scene_id = 1
        self.channel_id = 1
        self.chat_channel_id = 1
        self.logged_in = True
        self.running = True
        self.sent = []
        self._send_lock = threading.Lock()

    def send(self, message_id, message, packet_id=0):
        with self._send_lock:
            self.sent.append((message_id, message, packet_id))

    def responses(self, message_id):
        return [message for mid, message, _ in self.sent if mid == message_id]


class SocialConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        res_loader.init()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        db.exit()
        Config.DB_PATH = str(Path(self.tmp.name) / "social.db")
        Config.IN_MEMORY = False
        db.init()
        for player_id in (1, 2, 3, 4):
            db.db.execute(
                "INSERT INTO players(player_id, player_name, head, avatar_frame) VALUES (?, ?, ?, ?)",
                (player_id, f"player-{player_id}", 41000 + player_id, 700 + player_id),
            )

        self.sessions = {player_id: FakeSession(player_id) for player_id in (1, 2, 3, 4)}
        self.online = list(self.sessions.values())
        self.stack = contextlib.ExitStack()
        for module, attribute in (
            (friend_add, "get_session"),
            (friend_black, "get_session"),
            (friend_del, "get_session"),
            (friend_handle, "get_session"),
            (interval_join, "get_session"),
            (send_chat, "_gs"),
        ):
            self.stack.enter_context(
                patch.object(module, attribute, return_value=self.online)
            )
        self.achievement = self.stack.enter_context(
            patch.object(friend_handle.achieve_track, "report")
        )
        self.public_chat = self.stack.enter_context(patch.object(send_chat, "up_chat_msg"))

    def tearDown(self):
        try:
            self.stack.close()
        finally:
            db.exit()
            Config.DB_PATH = self.old_path
            Config.IN_MEMORY = self.old_memory
            self.tmp.cleanup()

    def status(self, player_id, friend_id):
        return db.get_friend_info(player_id, friend_id, "friend_status")[0]

    def add(self, sender, target, packet_id=1):
        sender.sent.clear()
        friend_add.Handler().handle(
            sender, FriendAddReq(player_id=target.player_id).SerializeToString(), packet_id
        )
        return sender.responses(MsgId.FriendAddRsp)[-1]

    def accept(self, recipient, applicant, agree=True, packet_id=1):
        friend_handle.Handler().handle(
            recipient,
            FriendHandleReq(player_id=applicant.player_id, is_agree=agree).SerializeToString(),
            packet_id,
        )
        return recipient.responses(MsgId.FriendHandleRsp)[-1]

    def make_friends(self, first=None, second=None):
        first = first or self.sessions[1]
        second = second or self.sessions[2]
        self.assertEqual(self.add(first, second).status, StatusCode.StatusCode_OK)
        self.assertEqual(self.accept(second, first).status, StatusCode.StatusCode_OK)
        self.assertEqual(self.status(first.player_id, second.player_id), social.FRIEND_OK)
        self.assertEqual(self.status(second.player_id, first.player_id), social.FRIEND_OK)

    def send(self, sender, receiver, text, packet_id=1):
        sender.sent.clear()
        send_chat.Handler().handle(
            sender,
            SendChatMsgReq(
                type=ChatChannelType.ChatChannel_Private,
                player_id=receiver.player_id,
                text=text,
            ).SerializeToString(),
            packet_id,
        )
        return sender.responses(MsgId.SendChatMsgRsp)[-1]

    def read_history(self, reader, target, packet_id=1):
        reader.sent.clear()
        private_record.Handler().handle(
            reader,
            PrivateChatMsgRecordReq(target_player_id=target.player_id).SerializeToString(),
            packet_id,
        )
        return reader.responses(MsgId.PrivateChatMsgRecordRsp)[-1]

    def raw_history(self, first_id, second_id):
        raw = db.get_kv(0, "chat_private", social.pair_key(first_id, second_id), b"")
        return pickle.loads(raw) if raw else []

    def test_application_direction_duplicate_and_reverse_accept(self):
        first, second = self.sessions[1], self.sessions[2]
        self.assertEqual(self.add(first, second).status, StatusCode.StatusCode_OK)
        self.assertEqual(self.status(1, 2), social.FRIEND_NONE)
        self.assertEqual(self.status(2, 1), social.FRIEND_APPLY)
        self.assertEqual(len(second.responses(MsgId.FriendHandleNotice)), 1)

        self.assertEqual(
            self.add(first, second).status, StatusCode.StatusCode_FRIEND_APPLY_EXIST
        )
        self.assertEqual(len(second.responses(MsgId.FriendHandleNotice)), 1)
        # 原申请方不能替接收方接受自己的申请。
        self.assertEqual(
            self.accept(first, second).status, StatusCode.StatusCode_FRIEND_NOT_APPLY
        )
        self.assertEqual(self.status(2, 1), social.FRIEND_APPLY)

        self.assertEqual(self.accept(second, first).status, StatusCode.StatusCode_OK)
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (2, 2))
        self.assertEqual(self.achievement.call_count, 1)
        self.assertEqual(len(first.responses(MsgId.FriendHandleNotice)), 1)
        self.assertEqual(len(second.responses(MsgId.FriendHandleNotice)), 2)
        self.assertEqual(
            self.accept(second, first).status, StatusCode.StatusCode_FRIEND_NOT_APPLY
        )
        self.assertEqual(self.achievement.call_count, 1)
        self.assertEqual(
            self.add(second, first).status, StatusCode.StatusCode_FRIEND_EXIST
        )

    def test_concurrent_duplicate_applications_create_one_relationship(self):
        first, second = self.sessions[1], self.sessions[2]
        barrier = threading.Barrier(8)

        def apply(index):
            barrier.wait()
            packet_id = index + 1
            friend_add.Handler().handle(
                first,
                FriendAddReq(player_id=second.player_id).SerializeToString(),
                packet_id,
            )
            return next(
                message.status
                for mid, message, pid in first.sent
                if mid == MsgId.FriendAddRsp and pid == packet_id
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            statuses = list(executor.map(apply, range(8)))
        self.assertEqual(statuses.count(StatusCode.StatusCode_OK), 1)
        self.assertEqual(statuses.count(StatusCode.StatusCode_FRIEND_APPLY_EXIST), 7)
        self.assertEqual(
            db.db.execute("SELECT COUNT(*) FROM friend WHERE player_id IN (1,2) AND friend_id IN (1,2)").fetchone()[0],
            2,
        )
        self.assertEqual(len(second.responses(MsgId.FriendHandleNotice)), 1)

    def test_simultaneous_reverse_applications_do_not_deadlock_or_duplicate(self):
        first, second = self.sessions[1], self.sessions[2]
        barrier = threading.Barrier(2)

        def apply(sender, target):
            barrier.wait()
            return self.add(sender, target).status

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(
                executor.map(
                    lambda pair: apply(*pair),
                    ((first, second), (second, first)),
                )
            )
        self.assertEqual(sorted(statuses), sorted((
            StatusCode.StatusCode_OK,
            StatusCode.StatusCode_FRIEND_APPLY_EXIST,
        )))
        self.assertEqual(
            db.db.execute("SELECT COUNT(*) FROM friend WHERE player_id IN (1,2) AND friend_id IN (1,2)").fetchone()[0],
            2,
        )

    def test_concurrent_acceptance_settles_once(self):
        first, second = self.sessions[1], self.sessions[2]
        self.assertEqual(self.add(first, second).status, StatusCode.StatusCode_OK)
        barrier = threading.Barrier(8)

        def accept(index):
            barrier.wait()
            packet_id = index + 1
            friend_handle.Handler().handle(
                second,
                FriendHandleReq(player_id=first.player_id, is_agree=True).SerializeToString(),
                packet_id,
            )
            return next(
                message.status
                for mid, message, pid in second.sent
                if mid == MsgId.FriendHandleRsp and pid == packet_id
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            statuses = list(executor.map(accept, range(8)))
        self.assertEqual(statuses.count(StatusCode.StatusCode_OK), 1)
        self.assertEqual(statuses.count(StatusCode.StatusCode_FRIEND_NOT_APPLY), 7)
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (2, 2))
        self.assertEqual(self.achievement.call_count, 1)
        # 一个原申请通知 + 一个 ADD 通知。
        self.assertEqual(len(second.responses(MsgId.FriendHandleNotice)), 2)
        self.assertEqual(len(first.responses(MsgId.FriendHandleNotice)), 1)

    def test_rejection_clears_both_directions_and_cannot_be_reversed(self):
        first, second = self.sessions[1], self.sessions[2]
        self.add(first, second)
        self.assertEqual(
            self.accept(first, second, agree=False).status,
            StatusCode.StatusCode_FRIEND_NOT_APPLY,
        )
        self.assertEqual(self.status(2, 1), social.FRIEND_APPLY)
        self.assertEqual(self.accept(second, first, agree=False).status, StatusCode.StatusCode_OK)
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (0, 0))
        notices = second.responses(MsgId.FriendHandleNotice)
        self.assertEqual(len(notices), 2)  # 原申请通知 + 本地拒绝删除通知
        self.assertEqual(notices[-1].target_player_id, first.player_id)
        self.assertEqual(
            self.accept(second, first).status, StatusCode.StatusCode_FRIEND_NOT_APPLY
        )

    def test_failed_acceptance_rolls_back_both_rows_and_sends_no_notice(self):
        first, second = self.sessions[1], self.sessions[2]
        self.add(first, second)
        first.sent.clear()
        second.sent.clear()
        original = social._set_status
        calls = 0

        def fail_second_write(player_id, friend_id, status):
            nonlocal calls
            original(player_id, friend_id, status)
            calls += 1
            if calls == 2:
                raise RuntimeError("synthetic acceptance failure")

        with patch.object(social, "_set_status", side_effect=fail_second_write):
            with self.assertRaisesRegex(RuntimeError, "synthetic acceptance failure"):
                friend_handle.Handler().handle(
                    second,
                    FriendHandleReq(player_id=1, is_agree=True).SerializeToString(),
                    1,
                )
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (0, 1))
        self.assertEqual(first.sent, [])
        self.assertEqual(second.sent, [])
        self.achievement.assert_not_called()

    def test_failed_application_rolls_back_initialized_pair(self):
        first, second = self.sessions[1], self.sessions[2]
        first.sent.clear()
        second.sent.clear()
        with patch.object(social, "_set_status", side_effect=RuntimeError("synthetic apply failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic apply failure"):
                friend_add.Handler().handle(
                    first, FriendAddReq(player_id=2).SerializeToString(), 1
                )
        self.assertEqual(
            db.db.execute("SELECT COUNT(*) FROM friend WHERE player_id IN (1,2) AND friend_id IN (1,2)").fetchone()[0],
            0,
        )
        self.assertEqual(first.sent, [])
        self.assertEqual(second.sent, [])

    def test_failed_delete_and_blacklist_roll_back_both_rows(self):
        for operation in ("delete", "black"):
            with self.subTest(operation=operation):
                # 每个子用例重新建立好友，且清理上一条通知。
                db.db.execute("DELETE FROM friend WHERE player_id IN (1,2) AND friend_id IN (1,2)")
                first, second = self.sessions[1], self.sessions[2]
                first.sent.clear()
                second.sent.clear()
                self.make_friends()
                first.sent.clear()
                second.sent.clear()
                original = social._set_status
                calls = 0

                def fail_second_write(player_id, friend_id, status):
                    nonlocal calls
                    original(player_id, friend_id, status)
                    calls += 1
                    if calls == 2:
                        raise RuntimeError("synthetic relationship failure")

                with patch.object(social, "_set_status", side_effect=fail_second_write):
                    with self.assertRaisesRegex(RuntimeError, "synthetic relationship failure"):
                        if operation == "delete":
                            friend_del.Handler().handle(
                                first, FriendDelReq(player_id=2).SerializeToString(), 1
                            )
                        else:
                            friend_black.Handler().handle(
                                first, FriendBlackReq(player_id=2).SerializeToString(), 1
                            )
                self.assertEqual((self.status(1, 2), self.status(2, 1)), (2, 2))
                self.assertEqual(first.sent, [])
                self.assertEqual(second.sent, [])

    def test_blacklist_is_effective_in_both_directions_and_choices_are_independent(self):
        first, second = self.sessions[1], self.sessions[2]
        friend_black.Handler().handle(
            second, FriendBlackReq(player_id=1).SerializeToString(), 1
        )
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (0, 3))
        self.assertEqual(
            self.add(first, second).status, StatusCode.StatusCode_FRIEND_BLACK
        )
        self.assertEqual(
            self.send(first, second, "blocked").status,
            StatusCode.StatusCode_FRIEND_BLACK,
        )
        self.assertEqual(
            self.read_history(first, second).status,
            StatusCode.StatusCode_FRIEND_BLACK,
        )
        self.assertEqual(self.raw_history(1, 2), [])
        self.public_chat.assert_not_called()

        friend_black.Handler().handle(
            second, FriendBlackReq(player_id=1, is_remove=True).SerializeToString(), 2
        )
        self.make_friends()
        first.sent.clear()
        second.sent.clear()
        friend_black.Handler().handle(
            first, FriendBlackReq(player_id=2).SerializeToString(), 3
        )
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (3, 0))
        self.assertEqual(len(first.responses(MsgId.FriendHandleNotice)), 1)
        self.assertEqual(len(second.responses(MsgId.FriendHandleNotice)), 1)
        self.assertEqual(
            self.add(second, first).status, StatusCode.StatusCode_FRIEND_BLACK
        )

        # 双方各自拉黑后，解除一方不能解除另一方的拉黑。
        friend_black.Handler().handle(
            second, FriendBlackReq(player_id=1).SerializeToString(), 4
        )
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (3, 3))
        friend_black.Handler().handle(
            first, FriendBlackReq(player_id=2, is_remove=True).SerializeToString(), 5
        )
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (0, 3))
        self.assertEqual(
            self.add(first, second).status, StatusCode.StatusCode_FRIEND_BLACK
        )
        friend_black.Handler().handle(
            second, FriendBlackReq(player_id=1, is_remove=True).SerializeToString(), 6
        )
        self.assertEqual(self.add(first, second).status, StatusCode.StatusCode_OK)

    def test_blacklist_cancels_pending_application_atomically(self):
        first, second = self.sessions[1], self.sessions[2]
        self.add(first, second)
        friend_black.Handler().handle(
            second, FriendBlackReq(player_id=1).SerializeToString(), 1
        )
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (0, 3))
        self.assertEqual(
            self.accept(second, first).status, StatusCode.StatusCode_FRIEND_BLACK
        )

    def test_delete_preserves_history_and_unread_until_refriending(self):
        first, second = self.sessions[1], self.sessions[2]
        self.make_friends()
        self.assertEqual(self.send(first, second, "before-delete").status, StatusCode.StatusCode_OK)
        before = self.raw_history(1, 2)
        self.assertEqual(social.unread_count(2, 1), 1)

        first.sent.clear()
        second.sent.clear()
        friend_del.Handler().handle(
            first, FriendDelReq(player_id=2).SerializeToString(), 1
        )
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (0, 0))
        self.assertEqual(self.raw_history(1, 2), before)
        self.assertEqual(social.unread_count(2, 1), 1)
        self.assertEqual(len(first.responses(MsgId.FriendHandleNotice)), 1)
        self.assertEqual(len(second.responses(MsgId.FriendHandleNotice)), 1)
        self.assertEqual(
            self.read_history(second, first).status,
            StatusCode.StatusCode_FRIEND_NOT_EXIST,
        )
        self.assertEqual(social.unread_count(2, 1), 1)

        self.make_friends()
        response = self.read_history(second, first)
        self.assertEqual(response.status, StatusCode.StatusCode_OK)
        self.assertEqual([message.text for message in response.msg_record], ["before-delete"])
        self.assertEqual(social.unread_count(2, 1), 0)
        self.assertEqual(social.unread_count(1, 2), 0)

    def test_private_history_is_only_available_to_both_current_friends(self):
        first, second, outsider = self.sessions[1], self.sessions[2], self.sessions[3]
        self.make_friends()
        self.send(first, second, "private")
        response = self.read_history(outsider, second)
        self.assertEqual(response.status, StatusCode.StatusCode_FRIEND_NOT_EXIST)
        self.assertEqual(len(response.msg_record), 0)
        response = self.read_history(first, first)
        self.assertEqual(response.status, StatusCode.StatusCode_PLAYER_NOT_FOUND)
        self.assertEqual(len(response.msg_record), 0)

        # 历史存在但关系单向损坏时仍拒绝读取。
        db.set_friend_info(2, 1, "friend_status", social.FRIEND_NONE)
        response = self.read_history(first, second)
        self.assertEqual(response.status, StatusCode.StatusCode_FRIEND_NOT_EXIST)
        self.assertEqual(len(response.msg_record), 0)

    def test_private_send_rejects_missing_target_nonfriend_and_bad_expression(self):
        first, second, outsider = self.sessions[1], self.sessions[2], self.sessions[3]
        for target, expected in (
            (0, StatusCode.StatusCode_PLAYER_NOT_FOUND),
            (second.player_id, StatusCode.StatusCode_FRIEND_NOT_EXIST),
            (outsider.player_id, StatusCode.StatusCode_FRIEND_NOT_EXIST),
        ):
            first.sent.clear()
            send_chat.Handler().handle(
                first,
                SendChatMsgReq(
                    type=ChatChannelType.ChatChannel_Private,
                    player_id=target,
                    text="not-sent",
                ).SerializeToString(),
                1,
            )
            self.assertEqual(first.responses(MsgId.SendChatMsgRsp)[-1].status, expected)
        self.make_friends()
        first.sent.clear()
        send_chat.Handler().handle(
            first,
            SendChatMsgReq(
                type=ChatChannelType.ChatChannel_Private,
                player_id=2,
                text="bad-expression",
                expression=999999999,
            ).SerializeToString(),
            1,
        )
        self.assertEqual(
            first.responses(MsgId.SendChatMsgRsp)[-1].status,
            StatusCode.StatusCode_CFG_NOT_FOUND,
        )
        self.public_chat.assert_not_called()
        self.assertEqual(self.raw_history(1, 2), [])
        self.assertEqual(social.unread_count(2, 1), 0)

    def test_unread_belongs_to_receiver_and_survives_restart(self):
        first, second = self.sessions[1], self.sessions[2]
        self.make_friends()
        self.online.remove(second)
        self.assertEqual(self.send(first, second, "one").status, StatusCode.StatusCode_OK)
        self.assertEqual(self.send(first, second, "two", packet_id=2).status, StatusCode.StatusCode_OK)
        self.assertEqual(social.unread_count(1, 2), 0)
        self.assertEqual(social.unread_count(2, 1), 2)
        offline = social.private_chat_offline(2)
        self.assertEqual(len(offline), 1)
        self.assertEqual(offline[0]["player_id"], 1)
        self.assertTrue(offline[0]["is_new_msg"])
        self.assertEqual(offline[0]["avatar_frame"], 701)
        self.assertEqual(social.private_chat_offline(1), [])

        db.exit()
        db.init()
        self.assertEqual((self.status(1, 2), self.status(2, 1)), (2, 2))
        self.assertEqual(len(self.raw_history(1, 2)), 2)
        self.assertEqual(social.unread_count(2, 1), 2)
        self.assertEqual(social.private_chat_offline(2)[0]["player_id"], 1)

        response = self.read_history(second, first)
        self.assertEqual(response.status, StatusCode.StatusCode_OK)
        self.assertEqual([message.text for message in response.msg_record], ["two", "one"])
        self.assertEqual(social.unread_count(2, 1), 0)
        self.assertEqual(social.unread_count(1, 2), 0)
        self.assertEqual(social.private_chat_offline(2), [])

    def test_concurrent_private_sends_append_exactly_once_and_notify_receiver(self):
        first, second = self.sessions[1], self.sessions[2]
        self.make_friends()
        count = 24
        barrier = threading.Barrier(count)

        def send(index):
            barrier.wait()
            packet_id = index + 1
            send_chat.Handler().handle(
                first,
                SendChatMsgReq(
                    type=ChatChannelType.ChatChannel_Private,
                    player_id=second.player_id,
                    text=f"message-{index}",
                ).SerializeToString(),
                packet_id,
            )
            return next(
                message.status
                for mid, message, pid in first.sent
                if mid == MsgId.SendChatMsgRsp and pid == packet_id
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
            statuses = list(executor.map(send, range(count)))
        self.assertEqual(statuses, [StatusCode.StatusCode_OK] * count)
        history = self.raw_history(1, 2)
        self.assertEqual(len(history), count)
        self.assertEqual({message["text"] for message in history}, {
            f"message-{index}" for index in range(count)
        })
        self.assertEqual(social.unread_count(2, 1), count)
        self.assertEqual(social.unread_count(1, 2), 0)
        self.assertEqual(len(second.responses(MsgId.ChatMsgNotice)), count)

    def test_concurrent_private_retries_are_idempotent_across_restart(self):
        first, second = self.sessions[1], self.sessions[2]
        self.make_friends()
        barrier = threading.Barrier(8)
        packet_id = 77

        def retry(_):
            barrier.wait()
            send_chat.Handler().handle(
                first,
                SendChatMsgReq(
                    type=ChatChannelType.ChatChannel_Private,
                    player_id=2,
                    text="retry-me",
                ).SerializeToString(),
                packet_id,
            )
            return next(
                message.status
                for mid, message, pid in first.sent
                if mid == MsgId.SendChatMsgRsp and pid == packet_id
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            statuses = list(executor.map(retry, range(8)))
        self.assertEqual(statuses, [StatusCode.StatusCode_OK] * 8)
        self.assertEqual(len(self.raw_history(1, 2)), 1)
        self.assertEqual(social.unread_count(2, 1), 1)
        self.assertEqual(len(second.responses(MsgId.ChatMsgNotice)), 1)

        # 同一请求标识但内容不同必须冲突，不能覆盖首次消息。
        self.assertEqual(
            self.send(first, second, "different-content", packet_id).status,
            StatusCode.StatusCode_BAD_REQ,
        )
        self.assertEqual(len(self.raw_history(1, 2)), 1)
        self.assertEqual(social.unread_count(2, 1), 1)

        db.exit()
        db.init()
        self.assertEqual(
            self.send(first, second, "retry-me", packet_id).status,
            StatusCode.StatusCode_OK,
        )
        self.assertEqual(len(self.raw_history(1, 2)), 1)
        self.assertEqual(social.unread_count(2, 1), 1)
        self.assertEqual(len(second.responses(MsgId.ChatMsgNotice)), 1)

    def test_private_history_limit_and_unread_count_are_independent(self):
        first, second = self.sessions[1], self.sessions[2]
        self.make_friends()
        with patch.object(Config, "CHAT_HISTORY_MAX", 5):
            for index in range(8):
                self.assertEqual(
                    self.send(first, second, f"message-{index}", index + 1).status,
                    StatusCode.StatusCode_OK,
                )
        self.assertEqual(
            [message["text"] for message in self.raw_history(1, 2)],
            [f"message-{index}" for index in range(3, 8)],
        )
        self.assertEqual(social.unread_count(2, 1), 8)

    def test_failed_unread_write_rolls_back_history_and_notifications(self):
        first, second = self.sessions[1], self.sessions[2]
        self.make_friends()
        first.sent.clear()
        second.sent.clear()
        with patch.object(social.db, "incr_kv", side_effect=RuntimeError("synthetic unread failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic unread failure"):
                send_chat.Handler().handle(
                    first,
                    SendChatMsgReq(
                        type=ChatChannelType.ChatChannel_Private,
                        player_id=2,
                        text="must-rollback",
                    ).SerializeToString(),
                    1,
                )
        self.assertEqual(self.raw_history(1, 2), [])
        self.assertEqual(social.unread_count(2, 1), 0)
        self.assertEqual(first.sent, [])
        self.assertEqual(second.sent, [])
        self.public_chat.assert_not_called()

    def test_interval_join_requires_friend_and_is_idempotent_under_concurrency(self):
        first, second = self.sessions[1], self.sessions[2]
        now = 1_700_000_000_000
        original_finish = now + 100_000
        db.set_interval(2, {
            "interval_id": 99,
            "finish_time": original_finish,
            "create_time": now,
            "member": [],
        })
        cfg = {"retention_time": 3600, "member_count": 5, "time": 100}
        request = IntervalJoinReq(friend_id=2).SerializeToString()
        with patch.object(garden_state, "now_ms", return_value=now), \
             patch.object(garden_state, "interval_cfg", return_value=cfg):
            first.sent.clear()
            interval_join.Handler().handle(first, request, 1)
            self.assertEqual(
                first.responses(MsgId.IntervalJoinRsp)[-1].status,
                StatusCode.StatusCode_FRIEND_NOT_EXIST,
            )
            self.assertEqual(garden_state.get_interval(2)["member"], [])

            self.make_friends()
            first.sent.clear()
            barrier = threading.Barrier(2)

            def join(index):
                barrier.wait()
                packet_id = index + 1
                interval_join.Handler().handle(first, request, packet_id)
                return next(
                    message.status
                    for mid, message, pid in first.sent
                    if mid == MsgId.IntervalJoinRsp and pid == packet_id
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(join, range(2)))
            self.assertEqual(statuses, [StatusCode.StatusCode_OK, StatusCode.StatusCode_OK])
            info = garden_state.get_interval(2)
            self.assertEqual(len(info["member"]), 1)
            self.assertEqual(info["finish_time"], original_finish - 20_000)
            self.assertEqual(len(second.responses(MsgId.IntervalChangeNotice)), 1)

            db.exit()
            db.init()
            self.assertEqual(garden_state.get_interval(2)["finish_time"], original_finish - 20_000)
            first.sent.clear()
            interval_join.Handler().handle(first, request, 3)
            self.assertEqual(garden_state.get_interval(2)["finish_time"], original_finish - 20_000)
            self.assertEqual(len(garden_state.get_interval(2)["member"]), 1)

            friend_black.Handler().handle(
                second, FriendBlackReq(player_id=1).SerializeToString(), 1
            )
            first.sent.clear()
            interval_join.Handler().handle(first, request, 4)
            self.assertEqual(
                first.responses(MsgId.IntervalJoinRsp)[-1].status,
                StatusCode.StatusCode_FRIEND_BLACK,
            )

    def test_relation_lock_order_is_player_locks_then_database_transaction(self):
        events = []

        @contextlib.contextmanager
        def player_lock(player_id):
            events.append(("lock", player_id))
            yield

        @contextlib.contextmanager
        def transaction():
            events.append(("transaction",))
            yield

        with patch.object(social.item_mgr, "player_lock", side_effect=player_lock), \
             patch.object(social.db, "transaction", side_effect=transaction):
            self.assertEqual(
                social.request_friend(2, 1)[0], StatusCode.StatusCode_OK
            )
        self.assertEqual(events, [("lock", 1), ("lock", 2), ("transaction",)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
