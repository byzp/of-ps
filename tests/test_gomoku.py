import contextlib
import time
import unittest
from unittest.mock import patch

from config import Config
# 先初始化 db 模块，避免 pb_create/achieve_track 的既有循环导入顺序问题。
import utils.db as db
from network.msg_id import MsgId
from proto.net_pb2 import (
    CollapseFailReq,
    EGomokuChessBoardStatus,
    EGomokuOverReason,
    GetGomokuOnlineChessboardReq,
    GomokuOnlinePlayerLeaveReq,
    GomokuOnlinePlayerPlaceStoneReq,
    GomokuOnlinePlayerReadyReq,
    GomokuOnlinePlayerStartPlayReq,
    GomokuOnlinePlayerWatchReq,
    GomokuSinglePlayerRewardReq,
    PlayerBriefInfo,
    StatusCode,
)
from server import gomoku
import handlers.CollapseFail as collapse
import handlers.GetGomokuOnlineChessboard as get_board
import handlers.GomokuOnlinePlayerLeave as leave
import handlers.GomokuOnlinePlayerPlaceStone as place
import handlers.GomokuOnlinePlayerReady as ready
import handlers.GomokuOnlinePlayerStartPlay as start_play
import handlers.GomokuOnlinePlayerWatch as watch
import handlers.GomokuSinglePlayerReward as single


class FakeSession:
    def __init__(self, player_id, scene_id=9999, channel_id=1):
        self.player_id = player_id
        self.scene_id = scene_id
        self.channel_id = channel_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class SinglePlayerGomokuTests(unittest.TestCase):
    def setUp(self):
        gomoku.reset()

    def test_valid_win_is_detected_and_reward_claimed_once(self):
        session = FakeSession(1000000)
        board = [0] * 225
        for col in range(5):
            board[7 * 15 + col] = 1
        request = GomokuSinglePlayerRewardReq(board=board, self=1, last_row=7, last_col=4)
        with patch.object(Config, 'GOMOKU_SINGLE_PLAYER_REWARDS', ((101, 1),)), \
             patch.object(single.db, 'transaction', side_effect=contextlib.nullcontext), \
             patch.object(single.db, 'try_claim', return_value=True), \
             patch.object(single.item_mgr, 'grant_items') as grant:
            single.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_OK)
        self.assertTrue(session.sent[0][1].is_self_win)
        self.assertEqual(grant.call_count, 1)

    def test_invalid_last_move_is_rejected(self):
        session = FakeSession(1000000)
        request = GomokuSinglePlayerRewardReq(board=[0] * 225, self=1, last_row=7, last_col=4)
        single.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_BAD_REQ)

    def test_repeated_daily_claim_does_not_grant(self):
        session = FakeSession(1000000)
        board = [0] * 225
        for col in range(5):
            board[col] = 2
        request = GomokuSinglePlayerRewardReq(board=board, self=2, last_row=0, last_col=4)
        with patch.object(single.db, 'transaction', side_effect=contextlib.nullcontext), \
             patch.object(single.db, 'try_claim', return_value=False), \
             patch.object(single.item_mgr, 'grant_items') as grant:
            single.Handler().handle(session, request.SerializeToString(), 1)
        grant.assert_not_called()


class CollapseTests(unittest.TestCase):
    def test_failure_notifies_only_same_channel(self):
        source = FakeSession(1, scene_id=9999, channel_id=10)
        same = FakeSession(2, scene_id=9999, channel_id=10)
        other = FakeSession(3, scene_id=9999, channel_id=11)
        with patch.object(collapse, 'get_session', return_value=[source, same, other]), \
             patch.object(db, 'transaction', side_effect=contextlib.nullcontext), \
             patch.object(db, 'get_kv', return_value=None), \
             patch.object(db, 'set_kv'):
            collapse.Handler().handle(source, CollapseFailReq().SerializeToString(), 1)
        self.assertEqual(source.sent[0][0], MsgId.CollapseFailRsp)
        self.assertEqual([item[0] for item in same.sent], [MsgId.CollapseFailNotice])
        self.assertEqual(same.sent[0][1].player_id, 1)
        self.assertEqual(other.sent, [])


class OnlineGomokuTests(unittest.TestCase):
    def setUp(self):
        gomoku.reset()
        self.p1 = FakeSession(1)
        self.p2 = FakeSession(2)
        self.watcher = FakeSession(3)
        self.sessions = [self.p1, self.p2, self.watcher]
        self.get_sessions = patch.object(gomoku, 'get_session', return_value=self.sessions)
        self.get_sessions.start()
        self.addCleanup(self.get_sessions.stop)
        economy_patches = [
            patch.object(db, 'transaction', side_effect=contextlib.nullcontext),
            patch.object(gomoku.item_mgr, 'get_num', return_value=1000),
            patch.object(gomoku.item_mgr, 'consume_items', return_value=True),
            patch.object(gomoku.item_mgr, 'grant_single_item'),
            patch.object(db, 'get_kv', return_value=None),
            patch.object(db, 'set_kv'),
            patch.object(db, 'del_kv'),
            patch.object(db, 'try_claim', return_value=True),
        ]
        for economy_patch in economy_patches:
            economy_patch.start()
            self.addCleanup(economy_patch.stop)

    def ready_players(self):
        for session in (self.p1, self.p2):
            ready.Handler().handle(session, GomokuOnlinePlayerReadyReq(id=100, coin_num=10).SerializeToString(), 1)

    def start(self):
        self.ready_players()
        start_play.Handler().handle(self.p1, GomokuOnlinePlayerStartPlayReq(id=100).SerializeToString(), 1)
        self.assertEqual(self.p1.sent[-1][1].status, StatusCode.StatusCode_OK)

    def test_watch_and_board_snapshot(self):
        self.ready_players()
        watch.Handler().handle(self.watcher, GomokuOnlinePlayerWatchReq(id=100).SerializeToString(), 1)
        self.assertEqual(self.watcher.sent[0][1].status, StatusCode.StatusCode_OK)
        with patch.object(get_board, 'make_PlayerBriefInfo', side_effect=lambda player_id: PlayerBriefInfo(player_id=player_id)):
            get_board.Handler().handle(self.watcher, GetGomokuOnlineChessboardReq(id=100).SerializeToString(), 1)
        rsp = self.watcher.sent[-1][1]
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        self.assertEqual({item.player_id for item in rsp.chest_players}, {1, 2})
        self.assertEqual([item.player_id for item in rsp.watch_players], [3])

    def test_watcher_can_join_and_leave_as_player(self):
        ready.Handler().handle(self.p1, GomokuOnlinePlayerReadyReq(id=100).SerializeToString(), 1)
        watch.Handler().handle(self.p2, GomokuOnlinePlayerWatchReq(id=100).SerializeToString(), 1)
        ready.Handler().handle(self.p2, GomokuOnlinePlayerReadyReq(id=100).SerializeToString(), 2)
        self.assertNotIn(2, gomoku.get(100).watchers)
        start_play.Handler().handle(self.p1, GomokuOnlinePlayerStartPlayReq(id=100).SerializeToString(), 3)
        leave.Handler().handle(self.p2, GomokuOnlinePlayerLeaveReq(id=100).SerializeToString(), 4)
        self.assertEqual(gomoku.get(100).winner_id, 1)
        self.assertTrue(any(item[0] == MsgId.GomokuOnlinePlayerLeaveNotice and item[1].is_player for item in self.p1.sent))

    def test_alternating_moves_end_in_win_and_settlement(self):
        self.start()
        moves = [(7, 0), (0, 0), (7, 1), (0, 1), (7, 2), (0, 2), (7, 3), (0, 3), (7, 4)]
        for index, (row, col) in enumerate(moves):
            session = self.p1 if index % 2 == 0 else self.p2
            place.Handler().handle(session, GomokuOnlinePlayerPlaceStoneReq(id=100, row=row, col=col).SerializeToString(), 1)
        rsp = self.p1.sent[-1][1]
        self.assertTrue(rsp.is_win)
        board = gomoku.get(100)
        self.assertEqual(board.state, EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over)
        self.assertEqual(board.winner_id, 1)
        self.assertEqual(board.over_reason, EGomokuOverReason.EGomokuOverReason_Win)
        self.assertIn(MsgId.GomokuOnlineSettlementNotice, [item[0] for item in self.p1.sent])
        self.assertIn(MsgId.GomokuOnlinePlayerRemoveNotice, [item[0] for item in self.p2.sent])

    def test_leave_awards_opponent_and_broadcasts(self):
        self.start()
        leave.Handler().handle(self.p1, GomokuOnlinePlayerLeaveReq(id=100).SerializeToString(), 1)
        board = gomoku.get(100)
        self.assertEqual(board.winner_id, 2)
        self.assertEqual(board.over_reason, EGomokuOverReason.EGomokuOverReason_Leave)
        self.assertIn(MsgId.GomokuOnlinePlayerLeaveNotice, [item[0] for item in self.p2.sent])
        self.assertIn(MsgId.GomokuOnlineSettlementNotice, [item[0] for item in self.p2.sent])

    def test_turn_timeout_is_settled_lazily(self):
        self.start()
        board = gomoku.get(100)
        board.turn_deadline = int(time.time()) - 1
        with patch.object(get_board, 'make_PlayerBriefInfo', side_effect=lambda player_id: PlayerBriefInfo(player_id=player_id)):
            get_board.Handler().handle(self.p1, GetGomokuOnlineChessboardReq(id=100).SerializeToString(), 1)
        self.assertEqual(board.state, EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over)
        self.assertEqual(board.over_reason, EGomokuOverReason.EGomokuOverReason_Timeout)
        self.assertEqual(board.winner_id, 2)
        self.assertIn(MsgId.GomokuOnlineSettlementNotice, [item[0] for item in self.p2.sent])


if __name__ == '__main__':
    unittest.main(verbosity=2)
