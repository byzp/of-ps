from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as OverField_pb2
import proto.OverField_pb2 as StatusCode_pb2

@packet_handler(CmdId.PosterIllustrationListReq)
class PosterIllustrationListHandler(PacketHandler):
    def handle(self, session, data: bytes):
        rsp = OverField_pb2.PosterIllustrationListRsp()
        rsp.status = StatusCode_pb2.StatusCode_Ok

        """
        p1 = rsp.poster_illustrations.add()
        p1.poster_illustration_id = 1001
        p1.status = OverField_pb2.RewardStatus_Reward

        p2 = rsp.poster_illustrations.add()
        p2.poster_illustration_id = 1002
        p2.status = OverField_pb2.RewardStatus_NotReward

        p3 = rsp.poster_illustrations.add()
        p3.poster_illustration_id = 12345
        p3.status = OverField_pb2.RewardStatus_Reward
        """

        session.send(CmdId.PosterIllustrationListRsp, rsp)
