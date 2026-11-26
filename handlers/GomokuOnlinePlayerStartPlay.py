from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import EGomokuChessBoardStatus, GomokuOnlinePlayerStartPlayReq, GomokuOnlinePlayerStartPlayRsp, StatusCode
from server import gomoku


@packet_handler(MsgId.GomokuOnlinePlayerStartPlayReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GomokuOnlinePlayerStartPlayReq()
        req.ParseFromString(data)
        rsp = GomokuOnlinePlayerStartPlayRsp()
        board = gomoku.get(req.id, session.player_id)
        packs = {}
        started = (
            gomoku.start(board, pack_notices=packs)
            if board and session.player_id in board.players
            else False
        )
        if not started:
            if board is not None and board.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over:
                gomoku.send_settlement(board)
            rsp.status = (
                StatusCode.StatusCode_ITEM_NOT_ENOUGH
                if board is not None and board.start_error == 'funds'
                else StatusCode.StatusCode_BAD_REQ
            )
        else:
            rsp.status = StatusCode.StatusCode_OK
            rsp.turn_deadline = board.turn_deadline
            gomoku.send_packs(board, packs)
            gomoku.send_start_notice(board)
        session.send(MsgId.GomokuOnlinePlayerStartPlayRsp, rsp, packet_id)
