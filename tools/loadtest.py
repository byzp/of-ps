"""最小压测客户端：只做 TCP 连接 + 1007 心跳，用于验证"同时在线人数"上限。

协议：[u16 BE headLen][PacketHead][body]，PacketHead 是 protobuf。

用法：
    venv\\Scripts\\python.exe tools\\loadtest.py --host 127.0.0.1 --port 11033 --clients 100 --seconds 20
    venv\\Scripts\\python.exe tools\\loadtest.py --clients 100 --ramp 0.02   # 每 20ms 建一个连接

输出：连接成功率、心跳成功率、RTT p50/p95/p99/max，以及失败原因分布。
"""

import argparse
import socket
import struct
import statistics
import sys
import threading
import time

sys.path.insert(0, ".")

from proto.net_pb2 import PacketHead, PlayerPingReq  # noqa: E402

HDR = struct.Struct(">H")
PING_REQ = 1007
PING_RSP = 1008


def build_packet(msg_id, body, packet_id=0, seq=1):
    head = PacketHead()
    head.msg_id = msg_id
    head.packet_id = packet_id
    head.flag = 0
    head.body_len = len(body)
    head.seq_id = seq
    h = head.SerializeToString()
    return HDR.pack(len(h)) + h + body


def read_packet(sock):
    """读一个完整包，返回 (msg_id, body, 原始 head 长度)。超时抛 socket.timeout。"""
    head_len = HDR.unpack(read_exact(sock, 2))[0]
    head = PacketHead()
    head.ParseFromString(read_exact(sock, head_len))
    body = read_exact(sock, head.body_len) if head.body_len else b""
    return head.msg_id, body


def read_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed by peer")
        buf += chunk
    return buf


class Bot(threading.Thread):
    def __init__(self, index, host, port, seconds, interval, results, barrier):
        super().__init__(daemon=True)
        self.index = index
        self.host = host
        self.port = port
        self.seconds = seconds
        self.interval = interval
        self.results = results
        self.barrier = barrier
        self.rtts = []
        self.sent = 0
        self.errors = []

    def run(self):
        try:
            sock = socket.create_connection((self.host, self.port), timeout=5)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(5)
        except Exception as exc:  # 连不上直接记账
            self.results.append(("connect_fail", str(exc)))
            return

        deadline = time.time() + self.seconds
        try:
            self.barrier.wait(timeout=10)  # 所有 bot 同时开跑，制造峰值
        except Exception:
            pass

        try:
            while time.time() < deadline:
                req = PlayerPingReq()
                req.client_time_ms = int(time.time() * 1000)
                body = req.SerializeToString()
                t0 = time.perf_counter()
                try:
                    sock.sendall(build_packet(PING_REQ, body, seq=self.sent + 1))
                    self.sent += 1
                    msg_id, _ = read_packet(sock)
                    if msg_id != PING_RSP:
                        self.errors.append("unexpected msg %d" % msg_id)
                        continue
                    self.rtts.append((time.perf_counter() - t0) * 1000)
                except socket.timeout:
                    self.errors.append("timeout")
                    # 超时后连接状态不可信，重连一次
                    try:
                        sock.close()
                    except OSError:
                        pass
                    sock = socket.create_connection((self.host, self.port), timeout=5)
                    sock.settimeout(5)
                except Exception as exc:
                    self.errors.append("%s: %s" % (type(exc).__name__, exc))
                    break
                time.sleep(self.interval)
        finally:
            try:
                sock.close()
            except OSError:
                pass


def pct(values, p):
    if not values:
        return float("nan")
    k = max(0, min(len(values) - 1, int(round((len(values) - 1) * p))))
    return sorted(values)[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=11033)
    ap.add_argument("--clients", type=int, default=100)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--interval", type=float, default=1.0, help="心跳间隔秒")
    ap.add_argument("--ramp", type=float, default=0.0, help="建连间隔秒，0=同时")
    args = ap.parse_args()

    results = []
    barrier = threading.Barrier(args.clients)
    bots = [
        Bot(i, args.host, args.port, args.seconds, args.interval, results, barrier)
        for i in range(args.clients)
    ]

    t0 = time.time()
    for bot in bots:
        bot.start()
        if args.ramp:
            time.sleep(args.ramp)
    for bot in bots:
        bot.join(timeout=args.seconds + 15)
    elapsed = time.time() - t0

    all_rtt = [r for b in bots for r in b.rtts]
    sent = sum(b.sent for b in bots)
    errs = [e for b in bots for e in b.errors]
    conn_fail = sum(1 for r in results if r[0] == "connect_fail")
    silent = sum(1 for b in bots if b.sent == 0)

    print("=" * 62)
    print("客户端 %d，时长 %.0fs，总耗时 %.1fs" % (args.clients, args.seconds, elapsed))
    print("建连失败        : %d" % conn_fail)
    print("一个包都没发出去: %d  （被线程池排队、recv 没被调度）" % silent)
    print("心跳发出        : %d" % sent)
    print("收到响应        : %d" % len(all_rtt))
    print("成功率          : %.1f%%" % (100.0 * len(all_rtt) / sent if sent else 0))
    if errs:
        from collections import Counter

        for k, v in Counter(errs).most_common(5):
            print("  错误 %-40s x%d" % (k[:40], v))
    if all_rtt:
        print(
            "RTT(ms) p50=%.1f p95=%.1f p99=%.1f max=%.1f 平均=%.1f"
            % (
                pct(all_rtt, 0.50),
                pct(all_rtt, 0.95),
                pct(all_rtt, 0.99),
                max(all_rtt),
                statistics.mean(all_rtt),
            )
        )
    print("=" * 62)


if __name__ == "__main__":
    main()
