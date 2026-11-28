import time

from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import (
    GomokuSinglePlayerRewardReq,
    GomokuSinglePlayerRewardRsp,
    PackNotice,
    StatusCode,
)
from server import gomoku
import utils.db as db
from utils import item_mgr


@packet_handler(MsgId.GomokuSinglePlayerRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GomokuSinglePlayerRewardReq()
        req.ParseFromString(data)
        rsp = GomokuSinglePlayerRewardRsp()
        if (
            len(req.board) != gomoku.BOARD_SIZE * gomoku.BOARD_SIZE
            or req.self not in (1, 2)
            or not (0 <= req.last_row < gomoku.BOARD_SIZE)
            or not (0 <= req.last_col < gomoku.BOARD_SIZE)
            or any(value not in (0, 1, 2) for value in req.board)
        ):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GomokuSinglePlayerRewardRsp, rsp, packet_id)
            return
        index = req.last_row * gomoku.BOARD_SIZE + req.last_col
        if req.board[index] != req.self:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GomokuSinglePlayerRewardRsp, rsp, packet_id)
            return
        board = gomoku.Board(id=0, first_player_id=session.player_id, board=list(req.board))
        rsp.status = StatusCode.StatusCode_OK
        rsp.is_self_win = gomoku.is_winner(board, req.last_row, req.last_col, req.self)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        if rsp.is_self_win:
            rewards = Config.GOMOKU_SINGLE_PLAYER_REWARDS
            extra_rewards = Config.GOMOKU_SINGLE_PLAYER_EXTRA_REWARDS if req.is_use_game_coin else ()
            if rewards or extra_rewards:
                day = time.strftime('%Y-%m-%d', time.localtime())
                # 领取标记与奖励同事务提交，避免崩溃后出现已领取但未到账。
                with item_mgr.player_lock(session.player_id), db.transaction():
                    if db.try_claim(session.player_id, 'gomoku_single', day):
                        if rewards:
                            item_mgr.grant_items(
                                session.player_id,
                                rewards,
                                rsp_items=rsp.items,
                                pack_notice=pack,
                                session=session,
                            )
                        if extra_rewards:
                            item_mgr.grant_items(
                                session.player_id,
                                extra_rewards,
                                rsp_items=rsp.extra_rewards,
                                pack_notice=pack,
                                session=session,
                            )
        session.send(MsgId.GomokuSinglePlayerRewardRsp, rsp, packet_id)
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
