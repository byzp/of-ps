from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import SwitchGardenStatusReq, SwitchGardenStatusRsp, StatusCode
import utils.db as db
import utils.garden_state as garden_state
from utils.res_loader import res


def _password_expire_ms():
    if (
        "GlobalConfig" in res
        and "config" in res["GlobalConfig"]
        and "datas" in res["GlobalConfig"]["config"]
    ):
        for e in res["GlobalConfig"]["config"]["datas"]:
            if e.get("key") == "GardenPasswordExpireTime":
                if e.get("values"):
                    return int(e["values"][0]) * 1000
                return 72 * 3600 * 1000
    return 72 * 3600 * 1000


@packet_handler(MsgId.SwitchGardenStatusReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SwitchGardenStatusReq()
        req.ParseFromString(data)

        rsp = SwitchGardenStatusRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.is_open = req.is_open
        rsp.password = req.password

        # 持久化开放状态
        like_num, access_num, furniture_num, furniture_limit_num, _ = (
            db.get_garden_info(session.player_id)
        )
        db.set_garden_info(
            session.player_id,
            like_num,
            access_num,
            furniture_num,
            furniture_limit_num,
            req.is_open,
        )

        # 密码只保存在内存态
        if req.password:
            expire = garden_state.now_ms() + _password_expire_ms()
        else:
            expire = 0
        garden_state.set_garden_password(session.player_id, req.password, expire)
        rsp.password_expire_time = expire

        session.send(MsgId.SwitchGardenStatusRsp, rsp, packet_id)  # 1687,1688
