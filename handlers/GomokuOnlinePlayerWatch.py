from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import EGomokuChessBoardStatus, GomokuOnlinePlayerWatchReq, GomokuOnlinePlayerWatchRsp, StatusCode
from server import gomoku


@packet_handler(MsgId.GomokuOnlinePlayerWatchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GomokuOnlinePlayerWatchReq()
        req.ParseFromString(data)
        rsp = GomokuOnlinePlayerWatchRsp()
        board = gomoku.add_watcher(req.id, session.player_id)
        if board is None:
            rsp.status = StatusCode.StatusCode_BAD_REQ
        else:
            rsp.status = StatusCode.StatusCode_OK
            gomoku.send_watch_notice(board, session.player_id)
            if board.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over:
                gomoku.send_settlement(board)
        session.send(MsgId.GomokuOnlinePlayerWatchRsp, rsp, packet_id)
