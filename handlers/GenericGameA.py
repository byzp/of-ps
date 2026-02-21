from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    GenericGameAReq,
    GenericGameARsp,
    ItemDetail,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GenericGameAReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GenericGameAReq()
        req.ParseFromString(data)

        rsp = GenericGameARsp()
        rsp.status = StatusCode.StatusCode_OK

        match req.generic_msg_id:
            case 5:  # 解锁染色方案
                rsp1 = PackNotice()
                rsp1.status = StatusCode.StatusCode_OK
                cur_t = db.get_item_detail(session.player_id, 102)
                cur_item = ItemDetail()
                if not cur_t:
                    cur_item.CopyFrom(
                        make_item(
                            102,
                            0,
                            session.player_id,
                        )
                    )
                else:
                    cur_item.ParseFromString(cur_t)
                num = cur_item.main_item.base_item.num
                if num < 100:  # 使用菱石补齐星石
                    cur_t = db.get_item_detail(session.player_id, 108)
                    if not cur_t:
                        rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                        session.send(MsgId.GenericGameARsp, rsp, packet_id)
                        return
                    else:
                        item_t = ItemDetail()
                        item_t.ParseFromString(cur_t)
                        if item_t.main_item.base_item.num + num < 100:
                            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                            session.send(MsgId.GenericGameARsp, rsp, packet_id)
                            return
                        else:
                            item_t.main_item.base_item.num -= 100 - num
                            db.set_item_detail(
                                session.player_id,
                                item_t.SerializeToString(),
                                108,
                            )
                            cur_item.main_item.base_item.num = 0
                            db.set_item_detail(
                                session.player_id,
                                cur_item.SerializeToString(),
                                102,
                            )
                            rsp1.items.add().CopyFrom(item_t)
                            rsp1.items.add().CopyFrom(cur_item)
                else:
                    cur_item.main_item.base_item.num -= 100
                    db.set_item_detail(
                        session.player_id,
                        cur_item.SerializeToString(),
                        102,
                    )
                    rsp1.items.add().CopyFrom(cur_item)
                outfit = ItemDetail()
                outfit.ParseFromString(
                    db.get_item_detail(session.player_id, req.params[0].int_value)
                )
                ds = outfit.main_item.outfit.dye_schemes.add()
                ds.scheme_index = len(outfit.main_item.outfit.dye_schemes) - 1
                ds.is_un_lock = True
                db.set_item_detail(
                    session.player_id,
                    outfit.SerializeToString(),
                    req.params[0].int_value,
                )
                session.send(MsgId.PackNotice, rsp1, 0)
            case 7:  # 退出染色
                session.color_data[0] = None
            case 9:  # TODO 登录时是否进入热门频道，0为进入，1为不进入
                if req.params[0].int_value:
                    pass
            case _:
                print(req)
        session.send(MsgId.GenericGameARsp, rsp, packet_id)
