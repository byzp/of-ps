from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import SceneProcessListRsp, StatusCode

import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.SceneProcessListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SceneProcessListRsp()
        rsp.status = StatusCode.StatusCode_OK
        # 此接口返回完成的探索点数，成就类型113才使用万分比。
        for scene in res["Scene"]["scene_progress"]["datas"]:
            scene_id = scene["i_d"]
            count = int(db.get_kv(session.player_id, "ach", f"exp:{scene_id}", 0) or 0)
            if not count:
                continue
            entry = rsp.scene_process_list.add()
            entry.scene_id = scene_id
            entry.process = count
        session.send(MsgId.SceneProcessListRsp, rsp, packet_id)  # 1871,1872
