import concurrent.futures
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import (
    EGomokuChessBoardStatus,
    EGomokuOverReason,
    GomokuOnlinePlayerLeaveReq,
    GomokuOnlinePlayerPlaceStoneReq,
    GomokuOnlinePlayerReadyReq,
    GomokuOnlinePlayerStartPlayReq,
    GomokuOnlinePlayerWatchReq,
    ItemDetail,
    StatusCode,
)
from server import gomoku
# 先加载 db，稳定项目现有的 pb_create/achieve_track 导入顺序。
import utils.db as db
from utils import item_mgr
import handlers.GomokuOnlinePlayerLeave as leave
import handlers.GomokuOnlinePlayerPlaceStone as place
import handlers.GomokuOnlinePlayerReady as ready
import handlers.GomokuOnlinePlayerStartPlay as start_play
import handlers.GomokuOnlinePlayerWatch as watch


class FakeSession:
    def __init__(self, player_id):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))

    def responses(self, message_id):
        return [message for mid, message, _ in self.sent if mid == message_id]


class GomokuEconomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        db.exit()
        Config.DB_PATH = self.tmp.name + '/player.db'
        Config.IN_MEMORY = False
        db.init()
        for player_id in (1, 2, 3):
            db.db.execute(
                'INSERT INTO players(player_id, player_name) VALUES (?, ?)',
                (player_id, f'p{player_id}'),
            )
        self.p1 = FakeSession(1)
        self.p2 = FakeSession(2)
        self.watcher = FakeSession(3)
        self.sessions = [self.p1, self.p2, self.watcher]
        self.session_patch = patch.object(gomoku, 'get_session', return_value=self.sessions)
        self.session_patch.start()
        gomoku.reset()
        self.set_balance(1, 100)
        self.set_balance(2, 100)
        self.set_balance(3, 40)

    def tearDown(self):
        gomoku.reset()
        db.exit()
        self.session_patch.stop()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory
        self.tmp.cleanup()

    def set_balance(self, player_id, amount):
        detail = ItemDetail()
        detail.main_item.item_id = Config.GOMOKU_COIN_ITEM_ID
        detail.main_item.base_item.item_id = Config.GOMOKU_COIN_ITEM_ID
        detail.main_item.base_item.num = amount
        db.set_item_detail(
            player_id,
            detail.SerializeToString(),
            Config.GOMOKU_COIN_ITEM_ID,
        )

    def balance(self, player_id):
        return item_mgr.get_num(player_id, Config.GOMOKU_COIN_ITEM_ID)

    def ready(self, session, board_id=100, wager=30):
        request = GomokuOnlinePlayerReadyReq(id=board_id, coin_num=wager)
        ready.Handler().handle(session, request.SerializeToString(), 1)
        return session.responses(MsgId.GomokuOnlinePlayerReadyRsp)[-1]

    def start(self, board_id=100):
        request = GomokuOnlinePlayerStartPlayReq(id=board_id)
        start_play.Handler().handle(self.p1, request.SerializeToString(), 2)
        return self.p1.responses(MsgId.GomokuOnlinePlayerStartPlayRsp)[-1]

    def place(self, session, row, col, board_id=100):
        request = GomokuOnlinePlayerPlaceStoneReq(id=board_id, row=row, col=col)
        place.Handler().handle(session, request.SerializeToString(), 3)
        return session.responses(MsgId.GomokuOnlinePlayerPlaceStoneRsp)[-1]

    def ready_players(self, board_id=100, wager1=30, wager2=30):
        self.assertEqual(self.ready(self.p1, board_id, wager1).status, StatusCode.StatusCode_OK)
        self.assertEqual(self.ready(self.p2, board_id, wager2).status, StatusCode.StatusCode_OK)

    def win_with_horizontal_five(self):
        moves = [(7, 0), (0, 0), (7, 1), (0, 1), (7, 2), (0, 2), (7, 3), (0, 3), (7, 4)]
        for index, (row, col) in enumerate(moves):
            session = self.p1 if index % 2 == 0 else self.p2
            self.assertEqual(self.place(session, row, col).status, StatusCode.StatusCode_OK)

    def test_wager_bounds_and_repeat_ready_cannot_change_frozen_wager(self):
        self.assertIsNone(gomoku.create_or_join(100, 1, -1))
        self.assertIsNone(
            gomoku.create_or_join(100, 1, Config.GOMOKU_MAX_WAGER + 1)
        )
        self.assertEqual(
            self.ready(self.p1, 100, Config.GOMOKU_MAX_WAGER + 1).status,
            StatusCode.StatusCode_BAD_REQ,
        )
        self.assertIsNone(gomoku.get(100))

        self.assertEqual(self.ready(self.p1, 100, 30).status, StatusCode.StatusCode_OK)
        self.assertEqual(self.ready(self.p1, 100, 40).status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual(gomoku.get(100).wagers[1], 30)
        self.assertEqual(self.ready(self.p2, 100, 30).status, StatusCode.StatusCode_OK)
        self.assertEqual(self.ready(self.watcher, 100, 30).status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual((self.balance(1), self.balance(2)), (100, 100))

    def test_insufficient_balance_is_rejected_on_create_and_join(self):
        self.set_balance(1, 5)
        self.assertEqual(self.ready(self.p1, 100, 10).status, StatusCode.StatusCode_BAD_REQ)
        self.assertIsNone(gomoku.get(100))

        self.set_balance(1, 100)
        self.set_balance(2, 9)
        self.assertEqual(self.ready(self.p1, 101, 10).status, StatusCode.StatusCode_OK)
        self.assertEqual(self.ready(self.p2, 101, 10).status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual(gomoku.get(101).players, {1})
        self.assertEqual((self.balance(1), self.balance(2)), (100, 9))

    def test_join_rechecks_both_balances_without_half_joining(self):
        self.assertEqual(self.ready(self.p1, 100, 30).status, StatusCode.StatusCode_OK)
        self.assertTrue(item_mgr.consume_items(1, [(Config.GOMOKU_COIN_ITEM_ID, 80)]))
        self.assertEqual(self.ready(self.p2, 100, 30).status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual(gomoku.get(100).players, {1})
        self.assertNotIn(2, gomoku.get(100).wagers)
        self.assertEqual(self.ready(self.p1, 100, 30).status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual((self.balance(1), self.balance(2)), (20, 100))

    def test_start_is_atomic_when_second_player_balance_drops(self):
        self.ready_players()
        self.assertTrue(item_mgr.consume_items(2, [(Config.GOMOKU_COIN_ITEM_ID, 80)]))
        self.assertEqual(self.start().status, StatusCode.StatusCode_ITEM_NOT_ENOUGH)
        self.assertEqual((self.balance(1), self.balance(2)), (100, 20))
        board = gomoku.get(100)
        self.assertFalse(board.started)
        self.assertEqual(board.state, EGomokuChessBoardStatus.EGomokuChessBoardStatus_Start)
        self.assertIsNone(db.get_kv(0, gomoku._ROOM_NS, '100'))

        self.set_balance(2, 100)
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        self.assertEqual((self.balance(1), self.balance(2)), (70, 70))
        self.assertEqual(self.start().status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual((self.balance(1), self.balance(2)), (70, 70))
        self.assertEqual(len(self.p1.responses(MsgId.PackNotice)), 1)
        self.assertEqual(len(self.p2.responses(MsgId.PackNotice)), 1)

    def test_unequal_wagers_winner_takes_pot_and_repeated_settlement_is_noop(self):
        self.ready_players(wager1=30, wager2=20)
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        watch_handler = watch.Handler()
        watch_handler.handle(
            self.watcher,
            GomokuOnlinePlayerWatchReq(id=100).SerializeToString(),
            4,
        )
        self.win_with_horizontal_five()
        self.assertEqual((self.balance(1), self.balance(2), self.balance(3)), (120, 80, 40))
        self.assertFalse(gomoku.send_settlement(gomoku.get(100)))
        self.assertEqual(self.place(self.p1, 7, 5).status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual((self.balance(1), self.balance(2), self.balance(3)), (120, 80, 40))
        self.assertEqual(self.watcher.responses(MsgId.GomokuOnlineSettlementNotice), [])
        winner_notice = self.p1.responses(MsgId.GomokuOnlineSettlementNotice)[-1]
        self.assertTrue(winner_notice.is_win)
        self.assertEqual(winner_notice.items[0].main_item.base_item.num, 50)

    def test_full_board_draw_refunds_each_wager_once(self):
        self.ready_players(wager1=20, wager2=20)
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        board = gomoku.get(100)
        filled = [
            1 if (col + 2 * row) % 4 < 2 else 2
            for row in range(gomoku.BOARD_SIZE)
            for col in range(gomoku.BOARD_SIZE)
        ]
        filled[-1] = 0
        board.board = filled
        board.next_player_id = 2
        self.assertEqual(self.place(self.p2, 14, 14).status, StatusCode.StatusCode_OK)
        self.assertEqual(board.winner_id, 0)
        self.assertEqual(board.over_reason, Config.GOMOKU_DRAW_OVER_REASON)
        self.assertEqual((self.balance(1), self.balance(2)), (100, 100))
        for session in (self.p1, self.p2):
            notice = session.responses(MsgId.GomokuOnlineSettlementNotice)[-1]
            self.assertFalse(notice.is_win)
            self.assertEqual(notice.items[0].main_item.base_item.num, 20)
        self.assertFalse(gomoku.send_settlement(board))
        self.assertEqual((self.balance(1), self.balance(2)), (100, 100))

    def test_leave_forfeits_leaver_and_notifies_both_players(self):
        self.ready_players()
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        leave.Handler().handle(
            self.watcher,
            GomokuOnlinePlayerLeaveReq(id=100).SerializeToString(),
            5,
        )
        leave.Handler().handle(
            self.p1,
            GomokuOnlinePlayerLeaveReq(id=100).SerializeToString(),
            6,
        )
        board = gomoku.get(100)
        self.assertEqual(board.winner_id, 2)
        self.assertEqual(board.over_reason, EGomokuOverReason.EGomokuOverReason_Leave)
        self.assertEqual((self.balance(1), self.balance(2), self.balance(3)), (70, 130, 40))
        self.assertFalse(self.p1.responses(MsgId.GomokuOnlineSettlementNotice)[-1].is_win)
        self.assertTrue(self.p2.responses(MsgId.GomokuOnlineSettlementNotice)[-1].is_win)
        self.assertEqual(self.watcher.responses(MsgId.GomokuOnlineSettlementNotice), [])
        leave.Handler().handle(
            self.p1,
            GomokuOnlinePlayerLeaveReq(id=100).SerializeToString(),
            7,
        )
        self.assertEqual((self.balance(1), self.balance(2)), (70, 130))

    def test_timeout_forfeits_current_player_and_rejects_late_move(self):
        self.ready_players()
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        board = gomoku.get(100)
        board.turn_deadline = int(time.time()) - 1
        self.assertEqual(self.place(self.p1, 7, 7).status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual(board.winner_id, 2)
        self.assertEqual(board.over_reason, EGomokuOverReason.EGomokuOverReason_Timeout)
        self.assertEqual(sum(board.board), 0)
        self.assertEqual((self.balance(1), self.balance(2)), (70, 130))

    def test_disconnect_after_grace_is_treated_as_leave(self):
        self.ready_players()
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        board = gomoku.get(100)
        board.last_seen[1] = int(time.time()) - Config.GOMOKU_DISCONNECT_GRACE_SECONDS - 1
        board.turn_deadline = int(time.time()) + 60
        with patch.object(gomoku, 'get_session', return_value=[self.p2, self.watcher]):
            self.assertEqual(self.place(self.p2, 0, 0).status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual(board.over_reason, EGomokuOverReason.EGomokuOverReason_Leave)
        self.assertEqual(board.winner_id, 2)
        self.assertEqual((self.balance(1), self.balance(2)), (70, 130))

    def test_concurrent_moves_accept_only_one_legal_turn(self):
        self.ready_players(wager1=10, wager2=10)
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        barrier = threading.Barrier(2)

        def move(session, row, col):
            barrier.wait()
            return self.place(session, row, col).status

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(move, self.p1, 7, 0)
            second = executor.submit(move, self.p2, 0, 0)
            statuses = [first.result(), second.result()]
        self.assertEqual(statuses.count(StatusCode.StatusCode_OK), 1)
        self.assertEqual(statuses.count(StatusCode.StatusCode_BAD_REQ), 1)
        board = gomoku.get(100)
        self.assertEqual(sum(board.board), 1)
        self.assertEqual(board.next_player_id, 2)
        self.assertEqual((self.balance(1), self.balance(2)), (90, 90))

    def test_concurrent_settlement_calls_payout_only_once(self):
        self.ready_players()
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        board = gomoku.get(100)
        gomoku.finish_draw(board)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: gomoku.send_settlement(board), range(8)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual((self.balance(1), self.balance(2)), (100, 100))
        self.assertEqual(len(self.p1.responses(MsgId.GomokuOnlineSettlementNotice)), 1)
        self.assertEqual(len(self.p2.responses(MsgId.GomokuOnlineSettlementNotice)), 1)

    def test_failed_settlement_rolls_back_claim_and_coins(self):
        self.ready_players()
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        board = gomoku.get(100)
        gomoku.finish_draw(board)
        with patch.object(gomoku.item_mgr, 'grant_single_item', side_effect=RuntimeError('synthetic')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                gomoku.send_settlement(board)
        self.assertFalse(board.settled)
        self.assertEqual((self.balance(1), self.balance(2)), (70, 70))
        self.assertFalse(db.has_claimed(0, gomoku._SETTLEMENT_SYSTEM, board.round_id))
        self.assertTrue(gomoku.send_settlement(board))
        self.assertEqual((self.balance(1), self.balance(2)), (100, 100))

    def test_service_restart_refunds_active_round_and_reuses_clean_runtime(self):
        self.ready_players()
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        old_board = gomoku.get(100)
        old_round_id = old_board.round_id
        watch.Handler().handle(
            self.watcher,
            GomokuOnlinePlayerWatchReq(id=100).SerializeToString(),
            8,
        )
        gomoku.reset()
        db.exit()
        db.init()
        self.assertEqual((self.balance(1), self.balance(2)), (70, 70))
        self.assertEqual(gomoku.recover_interrupted(), 1)
        self.assertEqual(gomoku.recover_interrupted(), 0)
        self.assertEqual((self.balance(1), self.balance(2)), (100, 100))
        record = gomoku._load_record(old_round_id)
        self.assertEqual(record['status'], 'settled')
        self.assertEqual(record['over_reason'], Config.GOMOKU_RESTART_OVER_REASON)

        self.assertEqual(self.ready(self.p1, 100, 30).status, StatusCode.StatusCode_OK)
        new_board = gomoku.get(100)
        self.assertIsNot(new_board, old_board)
        self.assertNotEqual(new_board.round_id, old_round_id)
        self.assertEqual(new_board.watchers, set())
        self.assertEqual(sum(new_board.board), 0)
        self.assertEqual(new_board.wagers, {1: 30})

    def test_service_restart_does_not_repay_committed_result(self):
        self.ready_players()
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        self.win_with_horizontal_five()
        old_board = gomoku.get(100)
        old_round_id = old_board.round_id
        self.assertEqual((self.balance(1), self.balance(2)), (130, 70))
        gomoku.reset()
        db.exit()
        db.init()

        restored = gomoku.Board(
            id=100,
            first_player_id=1,
            player1_id=1,
            player2_id=2,
            wagers={1: 30, 2: 30},
            state=EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over,
            winner_id=1,
            over_reason=EGomokuOverReason.EGomokuOverReason_Win,
            round_id=old_round_id,
            started=True,
        )
        with gomoku.locked():
            gomoku._boards[100] = restored
        self.assertTrue(gomoku.send_settlement(restored))
        self.assertEqual((self.balance(1), self.balance(2)), (130, 70))
        self.assertEqual(self.p1.responses(MsgId.GomokuOnlineSettlementNotice)[-1].items, [])

    def test_zero_wager_game_cannot_create_or_remove_coins(self):
        self.ready_players(wager1=0, wager2=0)
        self.assertEqual(self.start().status, StatusCode.StatusCode_OK)
        self.win_with_horizontal_five()
        self.assertEqual((self.balance(1), self.balance(2)), (100, 100))
        self.assertGreaterEqual(self.balance(1), 0)
        self.assertGreaterEqual(self.balance(2), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
