from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import EGomokuChessBoardStatus, GetGomokuOnlineChessboardReq, GetGomokuOnlineChessboardRsp, StatusCode
from server import gomoku
from utils.pb_create import make_PlayerBriefInfo


@packet_handler(MsgId.GetGomokuOnlineChessboardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetGomokuOnlineChessboardReq()
        req.ParseFromString(data)
        rsp = GetGomokuOnlineChessboardRsp()
        with gomoku.locked():
            board = gomoku.get(req.id, session.player_id)
            if board is None:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.GetGomokuOnlineChessboardRsp, rsp, packet_id)
                return
            rsp.status = StatusCode.StatusCode_OK
            rsp.board_state = board.state
            rsp.next_player_id = board.next_player_id
            rsp.turn_deadline = board.turn_deadline
            rsp.board.extend(board.board)
            for player_id in sorted(board.players):
                rsp.chest_players.add().CopyFrom(make_PlayerBriefInfo(player_id))
            for player_id in sorted(board.watchers):
                rsp.watch_players.add().CopyFrom(make_PlayerBriefInfo(player_id))
        if board.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over:
            gomoku.send_settlement(board)
        session.send(MsgId.GetGomokuOnlineChessboardRsp, rsp, packet_id)
