from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import EGomokuChessBoardStatus, GomokuOnlinePlayerReadyReq, GomokuOnlinePlayerReadyRsp, StatusCode
from server import gomoku


@packet_handler(MsgId.GomokuOnlinePlayerReadyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GomokuOnlinePlayerReadyReq()
        req.ParseFromString(data)
        rsp = GomokuOnlinePlayerReadyRsp()
        if not gomoku.valid_wager(req.coin_num):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GomokuOnlinePlayerReadyRsp, rsp, packet_id)
            return
        previous = gomoku.get(req.id, session.player_id)
        if previous is not None and previous.state == EGomokuChessBoardStatus.EGomokuChessBoardStatus_Over:
            gomoku.send_settlement(previous)
        board = gomoku.create_or_join(req.id, session.player_id, req.coin_num)
        if board is None:
            rsp.status = StatusCode.StatusCode_BAD_REQ
        else:
            rsp.status = StatusCode.StatusCode_OK
            gomoku.send_room_notice(board)
        session.send(MsgId.GomokuOnlinePlayerReadyRsp, rsp, packet_id)
