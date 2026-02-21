from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as TakeOutHandingFurnitureReq_pb2
import proto.OverField_pb2 as TakeOutHandingFurnitureRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.TakeOutHandingFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TakeOutHandingFurnitureReq_pb2.TakeOutHandingFurnitureReq()
        req.ParseFromString(data)

        rsp = TakeOutHandingFurnitureRsp_pb2.TakeOutHandingFurnitureRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.furniture_id = req.furniture_id

        session.send(MsgId.TakeOutHandingFurnitureRsp, rsp, packet_id)

