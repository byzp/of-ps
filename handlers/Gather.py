from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import GatherReq, GatherRsp, StatusCode, ItemDetail, PackNotice
import utils.db as db
from utils import refresh
from utils.res_loader import res
from utils.pb_create import make_item
from utils import achieve_track, item_mgr
from utils.pb_create import make_Achieve


@packet_handler(MsgId.GatherReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GatherReq()
        req.ParseFromString(data)

        rsp = GatherRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.index = req.gather_item.index
        rsp.item_level = 1

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        for data in res.get("Gather", {}).get("gather", {}).get("datas", []):
            for info in data["gather_group_info"]:
                if info["reward"] == req.gather_item.reward:
                    # 采集类型: 1木/2花/3石/4虫/5水/6拾取(gather_rule 列名对应)
                    gtype = info.get("new_weapon_type", 0)
                    _type_cols = {
                        0: "wood_num",
                        1: "wood_num",
                        2: "flower_num",
                        3: "stone_num",
                        4: "butterfly_num",
                        5: "water_num",
                        6: "pick_num",
                    }
                    col = _type_cols.get(int(gtype), "wood_num")
                    rule = next(
                        iter(
                            res.get("Gather", {})
                            .get("gather_rule", {})
                            .get("datas", [])
                        ),
                        {},
                    )
                    limit = int(rule.get(col, 0) or 0)
                    day = refresh.day_index()
                    cnt = int(
                        db.get_kv(
                            session.player_id,
                            "gather_daily",
                            f"{col}:{day}",
                            0,
                        )
                        or 0
                    )
                    if limit and cnt >= limit:
                        rsp.status = StatusCode.StatusCode_GATHER_LIMIT
                        session.send(MsgId.GatherRsp, rsp, packet_id)
                        return
                    db.set_kv(
                        session.player_id,
                        "gather_daily",
                        f"{col}:{day}",
                        cnt + 1,
                    )
                    rsp.group_gather_limit.gather_group_id = data["i_d"]
                    gather_limit = rsp.group_gather_limit.gather_limit
                    gather_limit.gather_type = info["new_weapon_type"]
                    gather_limit.gather_num = cnt + 1
                    gather_limit.gather_limit_num = max(limit, 1)
                    rsp.scene_gather_limit.scene_id = session.scene_id
                    gather_limit_s = rsp.scene_gather_limit.gather_limits.add()
                    gather_limit_s.CopyFrom(gather_limit)
                    for gather_reward in (
                        res.get("Gather", {}).get("gather_reward", {}).get("datas", [])
                    ):
                        if gather_reward["i_d"] == info["reward"]:
                            if req.gather_item.is_lucky:
                                item_t = gather_reward["gather_reward_group_info"][1]
                            else:
                                item_t = gather_reward["gather_reward_group_info"][0]
                            item = db.get_item_detail(
                                session.player_id, item_t["item_i_d"]
                            )
                            tmp1 = ItemDetail()
                            if not item:
                                make_item(
                                    item_t["item_i_d"], 0, session.player_id, tmp1
                                )
                            else:
                                tmp1.ParseFromString(item)
                            num_t = tmp1.main_item.base_item.num
                            item_mgr.mark_new_item(session.player_id, tmp1)
                            tmp1.main_item.base_item.num = item_t["count"]
                            rsp.items.add().CopyFrom(tmp1)
                            tmp1.main_item.base_item.num = num_t + item_t["count"]
                            rsp1.items.add().CopyFrom(tmp1)
                            db.set_item_detail(
                                session.player_id,
                                tmp1.SerializeToString(),
                                item_t["item_i_d"],
                                None,
                            )
                            session.send(MsgId.GatherRsp, rsp, packet_id)
                            make_Achieve(session, item_t["item_i_d"])
                            achieve_track.report(
                                session,
                                "gather",
                                match=item_t["item_i_d"],
                                amount=item_t.get("count", 1),
                                wt=int(info.get("new_weapon_type", 0)),
                            )
                            session.send(MsgId.PackNotice, rsp1, 0)
                            return
        # 未命中任何采集点位配置: 回失败响应
        rsp.status = StatusCode.StatusCode_FAIL
        session.send(MsgId.GatherRsp, rsp, packet_id)
