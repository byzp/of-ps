from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import CollectMoonReq, CollectMoonRsp, StatusCode, PackNotice
import utils.db as db
from utils import item_mgr, achieve_track
from utils.res_loader import res

"""
# 收集祈愿月亮 2575 2576(官方抓包 pack0 1212 份 OK 样本实锤)
奖励恒为 祈愿碎片(124) x5; 同一 moon_id 重复收集回 BAD_REQ(仅 status+
moon_id, 不发奖); 未知 moon_id 同 BAD_REQ。客户端收集后自行更新本地列表,
官方全程无 CollectMoonInfoUpdateNotice(0 样本)。
moon_id 为 8 位 CollectionItem 条目(11001001 型, 前5位=11000+场景)。
"""


def _moon_known(moon_id) -> bool:
    for e in res.get("CollectionItem", {}).get("collection_item", {}).get("datas", ()):
        if e.get("i_d") == moon_id:
            return True
    return False


@packet_handler(MsgId.CollectMoonReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectMoonReq()
        req.ParseFromString(data)

        rsp = CollectMoonRsp()
        rsp.moon_id = req.moon_id

        raw = db.get_kv(session.player_id, "collected_moons", "ids", b"")
        ids = {x for x in raw.decode().split(",") if x}
        if str(req.moon_id) in ids or not _moon_known(req.moon_id):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.CollectMoonRsp, rsp, packet_id)
            return

        ids.add(str(req.moon_id))
        db.set_kv(
            session.player_id,
            "collected_moons",
            "ids",
            ",".join(sorted(ids, key=lambda x: int(x))).encode(),
        )
        rsp.status = StatusCode.StatusCode_OK

        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK
        with achieve_track.batch(session):
            item_mgr.grant_items(
                session.player_id,
                [(124, 5)],
                pack_notice=notice,
                rsp_items=rsp.rewards,
                session=session,
            )
            session.send(MsgId.CollectMoonRsp, rsp, packet_id)
            if len(notice.items):
                session.send(MsgId.PackNotice, notice, 0)
