from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import (
    GomokuOnlinePlayerLeaveNotice,
    GomokuOnlinePlayerLeaveReq,
    GomokuOnlinePlayerLeaveRsp,
    StatusCode,
)
from server import gomoku


@packet_handler(MsgId.GomokuOnlinePlayerLeaveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GomokuOnlinePlayerLeaveReq()
        req.ParseFromString(data)
        rsp = GomokuOnlinePlayerLeaveRsp()
        board = gomoku.get(req.id, session.player_id)
        result = gomoku.leave(board, session.player_id) if board else None
        if result is None:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GomokuOnlinePlayerLeaveRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        notice = GomokuOnlinePlayerLeaveNotice(
            status=StatusCode.StatusCode_OK,
            id=req.id,
            player_id=session.player_id,
            is_player=result['is_player'],
        )
        for other in gomoku.participants(board):
            other.send(MsgId.GomokuOnlinePlayerLeaveNotice, notice, 0)
        if result['finished'] or (
            board.started and board.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over
        ):
            gomoku.send_settlement(board)
        session.send(MsgId.GomokuOnlinePlayerLeaveRsp, rsp, packet_id)
