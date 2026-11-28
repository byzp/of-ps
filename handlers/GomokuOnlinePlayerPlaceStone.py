from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import EGomokuChessBoardStatus, GomokuOnlinePlayerPlaceStoneReq, GomokuOnlinePlayerPlaceStoneRsp, StatusCode
from server import gomoku


@packet_handler(MsgId.GomokuOnlinePlayerPlaceStoneReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GomokuOnlinePlayerPlaceStoneReq()
        req.ParseFromString(data)
        rsp = GomokuOnlinePlayerPlaceStoneRsp()
        board = gomoku.get(req.id, session.player_id)
        result = gomoku.place(board, session.player_id, req.row, req.col) if board else None
        if result is None:
            if board is not None and board.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over:
                gomoku.send_settlement(board)
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GomokuOnlinePlayerPlaceStoneRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        rsp.is_win = result['is_win']
        rsp.next_player_id = board.next_player_id
        rsp.turn_deadline = board.turn_deadline
        gomoku.send_place_notice(board, result)
        if result['is_win'] or result['is_draw']:
            gomoku.send_settlement(board)
        session.send(MsgId.GomokuOnlinePlayerPlaceStoneRsp, rsp, packet_id)
