from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import UploadFGBytesReq, UploadFGBytesRsp, StatusCode

import server.mp_team as mp_team


@packet_handler(MsgId.UploadFGBytesReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UploadFGBytesReq()
        req.ParseFromString(data)

        rsp = UploadFGBytesRsp()
        rsp.status = StatusCode.StatusCode_OK

        # UploadFGBytesNotice 只有 status 字段、不携带 bytes, 无法用它把数据转发给
        # 其他玩家; 这里先把最近一次上传的数据按玩家存进房间内存态备用。
        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is not None and team["room"] is not None:
                team["room"]["fg_bytes"][session.player_id] = req.info

        session.send(MsgId.UploadFGBytesRsp, rsp, packet_id)  # 2521,2522 上传FG数据
