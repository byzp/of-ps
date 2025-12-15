from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as SetFriendExtInfoRsp_pb2
import proto.OverField_pb2 as SetFriendExtInfoReq_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db


@packet_handler(MsgId.SetFriendExtInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SetFriendExtInfoReq_pb2.SetFriendExtInfoReq()
        req.ParseFromString(data)

        rsp = SetFriendExtInfoRsp_pb2.SetFriendExtInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.player_id = req.player_id
        rsp.data.extend(req.data)

        for data_item in req.data:
            if data_item.type == 2:  # friend_tag 标签称号
                db.set_friend_info(
                    session.player_id, req.player_id, "friend_tag", data_item.int_value
                )
            elif data_item.type == 3:  # friend_background 标签底图
                db.set_friend_info(
                    session.player_id,
                    req.player_id,
                    "friend_background",
                    data_item.int_value,
                )

        session.send(
            MsgId.SetFriendExtInfoRsp, rsp, packet_id
        )  # 1781 1782 好友亲密标签
