import json
import threading
import time
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field

from config import Config
from proto.net_pb2 import (
    EGomokuChessBoardStatus,
    EGomokuOverReason,
    GomokuOnlinePlayerNotice,
    GomokuOnlinePlayerPlaceStoneNotice,
    GomokuOnlinePlayerRemoveNotice,
    GomokuOnlinePlayerStartPlayNotice,
    GomokuOnlinePlayerWatchNotice,
    GomokuOnlineSettlementNotice,
    PackNotice,
    StatusCode,
)
from network.msg_id import MsgId
from server.scene_data import get_session
import utils.db as db
from utils import item_mgr

BOARD_SIZE = 15
_lock = threading.RLock()
_boards = {}
_recovery_checked = False

# 只借用现有 player_kv/claimed_rewards 表，不增加数据库结构。
# 0 号玩家是数据库初始化时建立的系统记录，用于跨房间检索和全局幂等。
_SYSTEM_PLAYER_ID = 0
_ROUND_NS = 'gomoku_round'
_ROOM_NS = 'gomoku_room'
_SETTLEMENT_SYSTEM = 'gomoku_settlement'
_RECORD_VERSION = 1


class _InsufficientWager(Exception):
    pass


def locked():
    return _lock


@dataclass
class Board:
    id: int
    first_player_id: int
    player1_id: int = 0
    player2_id: int = 0
    watchers: set = field(default_factory=set)
    wagers: dict = field(default_factory=dict)
    board: list = field(default_factory=lambda: [0] * (BOARD_SIZE * BOARD_SIZE))
    state: int = EGomokuChessBoardStatus.EGomokuChessBoardStatus_Start
    next_player_id: int = 0
    turn_deadline: int = 0
    winner_id: int = 0
    over_reason: int = EGomokuOverReason.EGomokuOverReason_None
    round_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started: bool = False
    settled: bool = False
    settlement: dict = None
    start_error: str = ''
    last_seen: dict = field(default_factory=dict)

    @property
    def players(self):
        return {player for player in (self.player1_id, self.player2_id) if player}

    @property
    def wager_players(self):
        # 离开后 player1/player2 会被清理，原始下注玩家必须保留到结算完成。
        return tuple(sorted(player for player in self.wagers if player))


@contextmanager
def _player_locks(player_ids):
    """所有跨玩家收支都按 ID 排序持锁，且先于数据库事务。"""
    with ExitStack() as stack:
        for player_id in sorted(set(player_ids)):
            stack.enter_context(item_mgr.player_lock(player_id))
        yield


def valid_wager(coin_num):
    return isinstance(coin_num, int) and 0 <= coin_num <= Config.GOMOKU_MAX_WAGER


def reset():
    """只清理进程内 runtime；持久化流水由 recover_interrupted 保守退款。"""
    global _recovery_checked
    with _lock:
        _boards.clear()
        _recovery_checked = False


def get(board_id, player_id=None):
    with _lock:
        recover_interrupted()
        board = _boards.get(int(board_id))
        if board is not None:
            if player_id in board.wager_players:
                board.last_seen[player_id] = int(time.time())
            expire(board)
        return board


def _decode_record(raw):
    if not raw:
        return None
    try:
        record = json.loads(raw)
        if not isinstance(record, dict) or record.get('version') != _RECORD_VERSION:
            return None
        player1_id = int(record['player1_id'])
        player2_id = int(record['player2_id'])
        wagers = {int(player): int(num) for player, num in record['wagers'].items()}
        if (
            player1_id <= 0
            or player2_id <= 0
            or player1_id == player2_id
            or set(wagers) != {player1_id, player2_id}
            or any(not valid_wager(num) for num in wagers.values())
        ):
            return None
        record['player1_id'] = player1_id
        record['player2_id'] = player2_id
        record['wagers'] = wagers
        return record
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _load_record(round_id):
    return _decode_record(db.get_kv(_SYSTEM_PLAYER_ID, _ROUND_NS, round_id))


def _save_record(record):
    payload = dict(record)
    payload['wagers'] = {str(player): num for player, num in record['wagers'].items()}
    db.set_kv(
        _SYSTEM_PLAYER_ID,
        _ROUND_NS,
        record['round_id'],
        json.dumps(payload, sort_keys=True).encode('utf-8'),
    )


def _refund_interrupted(record):
    """重启后无 runtime 的进行中局不猜胜者，双方退回各自本金。"""
    round_id = record['round_id']
    with _player_locks(record['wagers']), db.transaction():
        latest = _load_record(round_id)
        if latest is None or latest.get('status') != 'active':
            return False
        if db.try_claim(_SYSTEM_PLAYER_ID, _SETTLEMENT_SYSTEM, round_id):
            for player_id, wager in latest['wagers'].items():
                if wager <= 0:
                    continue
                item_mgr.grant_single_item(
                    player_id,
                    Config.GOMOKU_COIN_ITEM_ID,
                    num=wager,
                )
        latest['status'] = 'settled'
        latest['winner_id'] = 0
        latest['over_reason'] = Config.GOMOKU_RESTART_OVER_REASON
        latest['settled_at'] = int(time.time())
        _save_record(latest)
        board_id = str(record['board_id'])
        if db.get_kv(_SYSTEM_PLAYER_ID, _ROOM_NS, board_id) == round_id:
            db.del_kv(_SYSTEM_PLAYER_ID, _ROOM_NS, board_id)
    return True


def recover_interrupted():
    """首次五子棋请求时回收服务重启遗留的 escrow，重复调用无副作用。"""
    global _recovery_checked
    with _lock:
        if _recovery_checked or db.conn is None:
            return 0
        runtime_rounds = {board.round_id for board in _boards.values() if not board.settled}
        recovered = 0
        for key in db.get_kv_keys(_SYSTEM_PLAYER_ID, _ROOM_NS):
            board_id = str(key)
            round_id = db.get_kv(_SYSTEM_PLAYER_ID, _ROOM_NS, board_id)
            if not round_id or round_id in runtime_rounds:
                continue
            record = _load_record(round_id)
            if record is not None and record.get('status') == 'active':
                if _refund_interrupted(record):
                    recovered += 1
        _recovery_checked = True
        return recovered


def create_or_join(board_id, player_id, coin_num=0):
    if board_id <= 0 or player_id <= 0 or not valid_wager(coin_num):
        return None
    with _lock:
        recover_interrupted()
        board = _boards.get(board_id)
        if board is not None and board.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over:
            # 防止调用方绕过 handler 直接重开时遗漏旧局结算。
            send_settlement(board)
            board = None
        if board is None:
            candidate = Board(id=board_id, first_player_id=player_id, player1_id=player_id)
            candidate.wagers[player_id] = coin_num
            with _player_locks(candidate.players), db.transaction():
                if item_mgr.get_num(player_id, Config.GOMOKU_COIN_ITEM_ID) < coin_num:
                    return None
            candidate.last_seen[player_id] = int(time.time())
            _boards[board_id] = candidate
            return candidate

        if board.state != EGomokuChessBoardStatus.EGomokuChessBoardStatus_Start:
            return None
        if player_id in board.players:
            if board.wagers.get(player_id) != coin_num:
                return None
            slot = None
        elif not board.player1_id:
            slot = 'player1_id'
        elif not board.player2_id:
            slot = 'player2_id'
        else:
            return None

        # 先构造候选视图，校验失败时不留下半加入的房间或下注。
        candidate_wagers = dict(board.wagers)
        candidate_wagers[player_id] = coin_num
        candidate_players = set(candidate_wagers)
        with _player_locks(candidate_players), db.transaction():
            if any(
                item_mgr.get_num(other_id, Config.GOMOKU_COIN_ITEM_ID)
                < candidate_wagers.get(other_id, 0)
                for other_id in candidate_players
            ):
                return None
        if slot is not None:
            setattr(board, slot, player_id)
        board.wagers = candidate_wagers
        board.last_seen[player_id] = int(time.time())
        board.watchers.discard(player_id)
        return board


def add_watcher(board_id, player_id):
    with _lock:
        board = get(board_id, player_id)
        if board is None or player_id <= 0:
            return None
        if player_id not in board.players:
            board.watchers.add(player_id)
        return board


def start(board, pack_notices=None):
    if board is None:
        return False
    with _lock:
        if len(board.players) != 2 or board.state != EGomokuChessBoardStatus.EGomokuChessBoardStatus_Start:
            board.start_error = 'state'
            return False
        players = board.wager_players
        if len(players) != 2 or any(not valid_wager(board.wagers.get(player)) for player in players):
            board.start_error = 'wager'
            return False
        packs = {}
        try:
            with _player_locks(players), db.transaction():
                # 先整体校验，任何一方不足都不产生另一方的部分扣除。
                if any(
                    item_mgr.get_num(player, Config.GOMOKU_COIN_ITEM_ID) < board.wagers[player]
                    for player in players
                ):
                    board.start_error = 'funds'
                    return False
                for player in players:
                    pack = PackNotice(status=StatusCode.StatusCode_OK)
                    if not item_mgr.consume_items(
                        player,
                        [(Config.GOMOKU_COIN_ITEM_ID, board.wagers[player])],
                        pack_notice=pack,
                    ):
                        raise _InsufficientWager(player)
                    packs[player] = pack
                record = _load_record(board.round_id) or {
                    'version': _RECORD_VERSION,
                    'round_id': board.round_id,
                    'board_id': board.id,
                    'player1_id': board.player1_id,
                    'player2_id': board.player2_id,
                    'first_player_id': board.first_player_id,
                    'wagers': dict(board.wagers),
                }
                record.update(status='active', started_at=int(time.time()))
                _save_record(record)
                db.set_kv(_SYSTEM_PLAYER_ID, _ROOM_NS, str(board.id), board.round_id)
        except _InsufficientWager:
            board.start_error = 'funds'
            return False

        now = int(time.time())
        board.started = True
        board.start_error = ''
        board.state = EGomokuChessBoardStatus.EGomokuChessBoardStatus_Playing
        board.next_player_id = (
            board.first_player_id
            if board.first_player_id in board.players
            else board.player1_id
        )
        board.turn_deadline = now + Config.GOMOKU_TURN_SECONDS
        board.last_seen = {player: now for player in players}
        if pack_notices is not None:
            pack_notices.update(packs)
        return True


def is_winner(board, row, col, chess):
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))
    for dr, dc in directions:
        count = 1
        for sign in (-1, 1):
            r, c = row + sign * dr, col + sign * dc
            while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board.board[r * BOARD_SIZE + c] == chess:
                count += 1
                r += sign * dr
                c += sign * dc
        if count >= 5:
            return True
    return False


def _finish(board, winner_id, over_reason):
    board.state = EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over
    board.winner_id = winner_id
    board.over_reason = over_reason
    board.next_player_id = 0
    board.turn_deadline = 0


def finish_draw(board):
    if board is None or board.state != EGomokuChessBoardStatus.EGomokuChessBoardStatus_Playing:
        return False
    _finish(board, 0, Config.GOMOKU_DRAW_OVER_REASON)
    return True


def place(board, player_id, row, col):
    if board is None or board.state != EGomokuChessBoardStatus.EGomokuChessBoardStatus_Playing:
        return None
    if player_id not in board.players or board.next_player_id != player_id:
        return None
    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        return None
    index = row * BOARD_SIZE + col
    if board.board[index]:
        return None
    chess = 1 if player_id == board.player1_id else 2
    board.board[index] = chess
    board.last_seen[player_id] = int(time.time())
    won = is_winner(board, row, col, chess)
    draw = not won and all(board.board)
    if won:
        _finish(board, player_id, EGomokuOverReason.EGomokuOverReason_Win)
    elif draw:
        _finish(board, 0, Config.GOMOKU_DRAW_OVER_REASON)
    else:
        board.next_player_id = board.player2_id if player_id == board.player1_id else board.player1_id
        board.turn_deadline = int(time.time()) + Config.GOMOKU_TURN_SECONDS
    return {'chess': chess, 'is_win': won, 'is_draw': draw, 'row': row, 'col': col}


def leave(board, player_id):
    if board is None:
        return None
    was_watcher = player_id in board.watchers
    board.watchers.discard(player_id)
    if player_id not in board.players:
        return {'is_player': False, 'finished': False} if was_watcher else None
    if board.player1_id == player_id:
        board.player1_id = 0
    else:
        board.player2_id = 0
    if board.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Playing:
        opponent = next(iter(board.players), 0)
        if Config.GOMOKU_LEAVE_FORFEITS and opponent:
            _finish(board, opponent, EGomokuOverReason.EGomokuOverReason_Leave)
        else:
            _finish(board, 0, Config.GOMOKU_DRAW_OVER_REASON)
        return {'is_player': True, 'finished': True}
    if board.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Start:
        board.wagers.pop(player_id, None)
        board.last_seen.pop(player_id, None)
    if not board.players and not board.started:
        _boards.pop(board.id, None)
    return {'is_player': True, 'finished': board.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over}


def expire(board):
    if board is None or board.state != EGomokuChessBoardStatus.EGomokuChessBoardStatus_Playing:
        return False
    now = time.time()
    if board.turn_deadline and now >= board.turn_deadline:
        loser = board.next_player_id
        winner = board.player2_id if loser == board.player1_id else board.player1_id
        if Config.GOMOKU_TIMEOUT_FORFEITS and winner in board.players:
            _finish(board, winner, EGomokuOverReason.EGomokuOverReason_Timeout)
        else:
            _finish(board, 0, Config.GOMOKU_DRAW_OVER_REASON)
        return True

    grace = Config.GOMOKU_DISCONNECT_GRACE_SECONDS
    if grace < 0:
        return False
    online = {session.player_id for session in get_session()}
    for player_id in board.wager_players:
        if player_id in online:
            continue
        if now - board.last_seen.get(player_id, now) < grace:
            continue
        opponent = board.player2_id if player_id == board.player1_id else board.player1_id
        if Config.GOMOKU_DISCONNECT_FORFEITS and opponent in board.players:
            _finish(board, opponent, EGomokuOverReason.EGomokuOverReason_Leave)
        else:
            _finish(board, 0, Config.GOMOKU_DRAW_OVER_REASON)
        return True
    return False


def _payouts(board):
    players = board.wager_players
    if len(players) != 2:
        return {}
    if board.winner_id in players:
        return {board.winner_id: sum(board.wagers.values())}
    return {player: board.wagers[player] for player in players}


def _settle_economy(board):
    if not board.started or not board.wager_players:
        return {'new': False, 'packs': {}, 'items': {}}
    payouts = _payouts(board)
    with _player_locks(board.wager_players), db.transaction():
        claimed = db.try_claim(_SYSTEM_PLAYER_ID, _SETTLEMENT_SYSTEM, board.round_id)
        packs = {}
        items = {}
        if claimed:
            for player_id, amount in payouts.items():
                if amount <= 0:
                    continue
                pack = PackNotice(status=StatusCode.StatusCode_OK)
                display = GomokuOnlineSettlementNotice()
                item_mgr.grant_single_item(
                    player_id,
                    Config.GOMOKU_COIN_ITEM_ID,
                    num=amount,
                    pack_notice=pack,
                    rsp_items=display.items,
                )
                packs[player_id] = pack
                items[player_id] = display
            if board.winner_id in payouts:
                for item_id, count in Config.GOMOKU_ONLINE_REWARDS:
                    if count <= 0:
                        continue
                    pack = packs.setdefault(
                        board.winner_id,
                        PackNotice(status=StatusCode.StatusCode_OK),
                    )
                    display = items.setdefault(
                        board.winner_id,
                        GomokuOnlineSettlementNotice(),
                    )
                    item_mgr.grant_single_item(
                        board.winner_id,
                        item_id,
                        num=count,
                        pack_notice=pack,
                        rsp_items=display.items,
                    )
            record = _load_record(board.round_id) or {
                'version': _RECORD_VERSION,
                'round_id': board.round_id,
                'board_id': board.id,
                'player1_id': board.wager_players[0],
                'player2_id': board.wager_players[1],
                'first_player_id': board.first_player_id,
                'wagers': dict(board.wagers),
            }
            record.update(
                status='settled',
                winner_id=board.winner_id,
                over_reason=board.over_reason,
                settled_at=int(time.time()),
            )
            _save_record(record)
        elif _load_record(board.round_id) is None:
            # 老 runtime 没有流水时也保留一条结算审计，避免重启后无法解释。
            record = {
                'version': _RECORD_VERSION,
                'round_id': board.round_id,
                'board_id': board.id,
                'player1_id': board.wager_players[0],
                'player2_id': board.wager_players[1],
                'first_player_id': board.first_player_id,
                'wagers': dict(board.wagers),
                'status': 'settled',
                'winner_id': board.winner_id,
                'over_reason': board.over_reason,
                'settled_at': int(time.time()),
            }
            _save_record(record)
    return {'new': claimed, 'packs': packs, 'items': items}


def settle(board):
    with _lock:
        if board is None or board.settled:
            return None
        result = _settle_economy(board)
        # 只有数据库事务成功提交后才允许内存标记完成。
        board.settlement = result
        board.settled = True
        return result


def participants(board):
    with _lock:
        player_ids = board.players | board.watchers | set(board.wager_players)
        return [session for session in get_session() if session.player_id in player_ids]


def send_packs(board, packs):
    if not packs:
        return
    for session in participants(board):
        pack = packs.get(session.player_id)
        if pack is not None and pack.items:
            session.send(MsgId.PackNotice, pack, 0)


def send_room_notice(board):
    notice = GomokuOnlinePlayerNotice(
        status=StatusCode.StatusCode_OK,
        first_player_id=board.first_player_id,
        player1_id=board.player1_id,
        player2_id=board.player2_id,
    )
    for session in participants(board):
        session.send(MsgId.GomokuOnlinePlayerNotice, notice, 0)


def send_watch_notice(board, player_id):
    notice = GomokuOnlinePlayerWatchNotice(
        status=StatusCode.StatusCode_OK,
        id=board.id,
        player_id=player_id,
    )
    for session in participants(board):
        session.send(MsgId.GomokuOnlinePlayerWatchNotice, notice, 0)


def send_start_notice(board):
    notice = GomokuOnlinePlayerStartPlayNotice(
        status=StatusCode.StatusCode_OK,
        id=board.id,
        first_player_id=board.next_player_id,
        turn_deadline=board.turn_deadline,
    )
    for session in participants(board):
        session.send(MsgId.GomokuOnlinePlayerStartPlayNotice, notice, 0)


def send_place_notice(board, result):
    notice = GomokuOnlinePlayerPlaceStoneNotice(
        status=StatusCode.StatusCode_OK,
        id=board.id,
        row=result['row'],
        col=result['col'],
        chess=result['chess'],
        next_player_id=board.next_player_id,
        turn_deadline=board.turn_deadline,
        is_win=result['is_win'],
    )
    for session in participants(board):
        session.send(MsgId.GomokuOnlinePlayerPlaceStoneNotice, notice, 0)


def send_settlement(board):
    with _lock:
        result = settle(board)
        if result is None:
            return False
    send_packs(board, result['packs'])
    for player_id in board.wager_players:
        notice = GomokuOnlineSettlementNotice(
            status=StatusCode.StatusCode_OK,
            id=board.id,
            is_win=player_id == board.winner_id,
            over_reason=board.over_reason,
        )
        display = result['items'].get(player_id)
        if display is not None:
            notice.items.extend(display.items)
        for session in participants(board):
            if session.player_id == player_id:
                session.send(MsgId.GomokuOnlineSettlementNotice, notice, 0)
    remove = GomokuOnlinePlayerRemoveNotice(
        status=StatusCode.StatusCode_OK,
        id=board.id,
        winner_id=board.winner_id,
        over_reason=board.over_reason,
    )
    for session in participants(board):
        session.send(MsgId.GomokuOnlinePlayerRemoveNotice, remove, 0)
    return True
