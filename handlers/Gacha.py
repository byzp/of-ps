from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import pickle

from proto.net_pb2 import (
    GachaReq,
    GachaRsp,
    StatusCode,
    PackNotice,
    ItemDetail,
    EBagItemTag,
)
from config import Config
from utils.res_loader import res
import utils.db as db
from utils import item_mgr
from utils import gacha_prob
from utils.pb_create import make_item
from utils import achieve_track


_QUALITY = None


def _quality_of(item_id):
    """物品品质：3=紫(SR) 4=金(SSR)，取 Item 表配置。"""
    global _QUALITY
    if _QUALITY is None:
        _QUALITY = {
            e.get("i_d"): int(e.get("quality", 0) or 0)
            for e in res["Item"]["item"]["datas"]
            if isinstance(e, dict)
        }
    return _QUALITY.get(item_id, 0)


@packet_handler(MsgId.GachaReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GachaReq()
        req.ParseFromString(data)

        with achieve_track.batch(session):
            self._draw(session, req, packet_id)

    def _info_row(self, gacha_id):
        for e in res["Gacha"]["info"]["datas"]:
            if isinstance(e, dict) and e.get("i_d") == gacha_id:
                return e
        return None

    def _optional(self, player_id, gacha_id):
        """读取玩家在该卡池的自选（ChooseGacha / OptionalUpPoolItem 写入 kv）。"""
        try:
            raw = db.get_kv(player_id, "gacha_optional_up", str(gacha_id))
            if raw:
                data = pickle.loads(raw)
                return int(data.get("item_id") or 0), int(data.get("pool_id") or 0)
        except Exception:
            pass
        return 0, 0

    def _draw(self, session, req, packet_id):
        rsp = GachaRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.info.gacha_id = req.gacha_id
        rsp.info.gacha_times = 1 if req.is_single else 10
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        info = self._info_row(req.gacha_id)
        type_id = int((info or {}).get("new_u_i_gacha_type") or 2)
        optional_item_id, choose_pool_id = self._optional(session.player_id, req.gacha_id)

        # 自选池：选了 up 池后，实际按所选池的配置抽（与官方 IsOptional 一致）
        draw_gacha_id = req.gacha_id
        if choose_pool_id and type_id in (6, 7, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19):
            if any(p["i_d"] == choose_pool_id for p in res["Gacha"]["pool"]["datas"]):
                draw_gacha_id = choose_pool_id
                info = self._info_row(draw_gacha_id) or info

        cost_paid = True
        pools_map = {}
        big_items = []
        if not info:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GachaRsp, rsp, packet_id)
            return

        # 单抽走 consume_item1(招募券), 十连走 consume_item2(星石)
        if req.is_single:
            cost_id = info.get("consume_item1_i_d", 0)
            cost_num = int(info.get("method1_count", 0) or 0) * int(
                info.get("consume_item1_num", 1) or 1
            )
        else:
            cost_id = info.get("consume_item2_i_d", 0)
            cost_num = int(info.get("consume_item2_num", 0) or 0)
        # 单抽成本缺失（新人池/免费池的 method1 配置为 0）时按免费单抽处理，
        # 不再直接 break 导致下面 rewards 为空、整包返回 CFG_NOT_FOUND。
        free_single = req.is_single and (not cost_id or cost_num <= 0)
        if not free_single and (not cost_id or cost_num <= 0):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GachaRsp, rsp, packet_id)
            return
        if not free_single:
            consume_b = db.get_item_detail(session.player_id, cost_id)
            if not consume_b:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.GachaRsp, rsp, packet_id)
                return
            item = rsp1.items.add()
            item.ParseFromString(consume_b)
            item.main_item.base_item.num -= cost_num
            if item.main_item.base_item.num < 0:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.GachaRsp, rsp, packet_id)
                return
            db.set_item_detail(
                session.player_id,
                item.SerializeToString(),
                item.main_item.item_id,
            )
            cost_paid = True

        # 收集本卡池可用的奖池（free_gacha_pool_i_d → item 列表）
        allowed = []
        for p in res["Gacha"]["pool"]["datas"]:
            if p["i_d"] == draw_gacha_id:
                allowed = [i2["free_gacha_pool_i_d"] for i2 in p["items"]]
                break
        if not allowed:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GachaRsp, rsp, packet_id)
            return
        for rp in res["Gacha"]["reward_pool"]["datas"]:
            if rp["i_d"] in allowed:
                pools_map[rp["i_d"]] = [i3["item_i_d"] for i3 in rp["items"]]
        gt_pool = int(info.get("big_guarantee_pool_i_d") or 0)
        if gt_pool:
            for rp in res["Gacha"]["reward_pool"]["datas"]:
                if rp["i_d"] == gt_pool:
                    big_items = [i3["item_i_d"] for i3 in rp["items"]]
                    break
        if not pools_map:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GachaRsp, rsp, packet_id)
            return

        # 官方概率 + 保底模型（按卡池独立计数，UP 保底必给本池 UP）
        draw_count = 1 if req.is_single else 10
        draws = gacha_prob.draw_batch(
            session.player_id,
            draw_gacha_id,
            type_id,
            info,
            pools_map,
            big_items,
            draw_count,
            optional_item_id=optional_item_id,
        )

        for r, kind in draws:
            # 兜底：模型算出的池缺失时，退回本卡池任意奖池随机
            if not r:
                all_items = [i for v in pools_map.values() for i in v]
                if not all_items:
                    continue
                r = all_items[0]
            # 新手池 2000 首抽固定给 102001（保留原逻辑）
            if (
                not Config.SKIP_QUESTS
                and draw_gacha_id == 2000
                and req.is_single
                and db.get_total_gacha_num(session.player_id, 2000) == 0
            ):
                r = 102001
            c = False
            for i in res["Character"]["character"]["datas"]:
                if i["i_d"] == r:
                    item = rsp.items.add()
                    # 重复角色自动转换为碎片(repeat_item_i_d)
                    dup = item_mgr.grant_character(
                        session.player_id, r, item, pack_notice=rsp1
                    )
                    if not dup:
                        extra = ItemDetail()
                        make_item(107, 500, session.player_id, extra)
                        item.extras.add().CopyFrom(extra.main_item)
                        item_mgr.grant_items(
                            session.player_id,
                            [(107, 500)],
                            pack_notice=rsp1,
                            session=session,
                        )
                        for i2 in res["Item"]["item"]["datas"]:
                            if i2["i_d"] == item.main_item.item_id:
                                item.extra_quality = i2.get("quality", 0)
                                break
                    else:
                        # 已拥有 → grant_character 把 item 换成了碎片。
                        # 抽卡展示需要「角色本体」，所以重建成角色卡，碎片放进 extras。
                        frag = ItemDetail()
                        frag.CopyFrom(item)
                        item.Clear()
                        item.main_item.item_id = r
                        item.main_item.item_tag = EBagItemTag.EBagItemTag_Card
                        blobs = db.get_characters(session.player_id, r)
                        if blobs:
                            item.main_item.character.ParseFromString(blobs[0])
                        item.main_item.is_new = False
                        item.extras.add().CopyFrom(frag.main_item)
                        item.extra_quality = _quality_of(r)
                    gacha_prob._dbg(
                        f"DRAW gacha={draw_gacha_id} type={type_id} want={r} kind={kind} "
                        f"dup={dup} out_id={item.main_item.item_id} "
                        f"out_tag={item.main_item.item_tag} is_new={item.main_item.is_new}"
                    )
                    c = True
                    break
            if not c:
                item_mgr.grant_single_item(
                    session.player_id,
                    r,
                    num=1,
                    rsp_items=rsp.items,
                    pack_notice=rsp1,
                )
            else:
                rsp1.items.add().CopyFrom(item)
            db.add_gacha_record(session.player_id, draw_gacha_id, r)

        # 兼容旧的按卡池保底显示（GachaList / OptionalUpPoolItem 读这张表）
        left = gacha_prob.remaining(session.player_id, draw_gacha_id, type_id, info)
        cap = gacha_prob.pity_cap(info, type_id)
        db.set_gacha_guarantee(session.player_id, req.gacha_id, max(0, cap - left))
        rsp.info.guarantee = left

        session.send(MsgId.GachaRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
        achieve_track.report(session, "gacha", amount=1 if req.is_single else 10)
