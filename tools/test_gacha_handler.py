"""离线验证 of-ps 的 Gacha handler（不经过网络，直接调 handler）。

用法（在 of-ps 目录下）：
    venv\\Scripts\\python.exe tools\\test_gacha_handler.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.res_loader as res_loader

res_loader.init()

import utils.db as db

db.init()

from proto.net_pb2 import GachaReq, GachaRsp, PackNotice, StatusCode

import handlers.Gacha as gacha_handler


class FakeSession:
    def __init__(self, player_id):
        self.player_id = player_id
        self.sent = []

    def send(self, msg_id, msg, packet_id=0, *a, **kw):
        self.sent.append((msg_id, msg, packet_id))


def run(gacha_id, is_single, player_id=10001, rounds=1):
    h = gacha_handler.Handler()
    for _ in range(rounds):
        req = GachaReq()
        req.gacha_id = gacha_id
        req.is_single = is_single
        s = FakeSession(player_id)
        h.handle(s, req.SerializeToString(), 1)
        rsp = None
        notice = None
        for mid, msg, _pid in s.sent:
            if isinstance(msg, GachaRsp):
                rsp = msg
            elif isinstance(msg, PackNotice):
                notice = msg
        print(f"--- gacha={gacha_id} single={is_single}")
        if rsp is None:
            print("  !! 没有 GachaRsp")
            continue
        print(f"  status={StatusCode.Name(rsp.status)} guarantee={rsp.info.guarantee} "
              f"times={rsp.info.gacha_times} items={len(rsp.items)}")
        for it in rsp.items:
            mid_ = it.main_item.item_id
            print(f"    item={mid_} num={it.main_item.base_item.num} extras={len(it.extras)}")
        if notice:
            print(f"  PackNotice items={len(notice.items)}")


if __name__ == "__main__":
    run(1000, True, rounds=3)   # 新人池，免费单抽
    run(1000, False, rounds=1)  # 十连（要 104×8 星石，可能不足）
    run(103005, True, rounds=1) # 限时 UP 池
    run(4000, True, rounds=1)   # 服装池
