from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as TakeOutFurnitureReq_pb2
import proto.OverField_pb2 as TakeOutFurnitureRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.TakeOutFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TakeOutFurnitureReq_pb2.TakeOutFurnitureReq()
        req.ParseFromString(data)

        rsp = TakeOutFurnitureRsp_pb2.TakeOutFurnitureRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK # TODO 验证家具是否存在, 官服也没做这个
        rsp.furniture_id = req.furniture_id

        session.send(MsgId.TakeOutFurnitureRsp, rsp, packet_id)

