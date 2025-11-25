#!/usr/bin/env python3
import socket
import struct
import time
from proto import OverField_pb2

HOST = "127.0.0.1"
PORT = 11033


def recvall(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return buf
        buf += chunk
    return buf


s = socket.socket()
s.connect((HOST, PORT))

seq = 0

while True:
    req = OverField_pb2.PlayerPingReq()
    send_ts = int(time.time() * 1000)
    req.client_time_ms = send_ts
    body = req.SerializeToString()

    head = OverField_pb2.PacketHead()
    head.msg_id = 1007  # PlayerPingReq
    head.flag = 0
    head.body_len = len(body)
    head.seq_id = seq
    head_data = head.SerializeToString()
    head_len = struct.pack(">H", len(head_data))

    s.sendall(head_len + head_data + body)

    hl = recvall(s, 2)
    hllen = struct.unpack(">H", hl)[0]
    head_bytes = recvall(s, hllen)
    rsp_head = OverField_pb2.PacketHead()
    rsp_head.ParseFromString(head_bytes)

    body_bytes = recvall(s, rsp_head.body_len)
    if rsp_head.flag == 1:
        import snappy

        body_bytes = snappy.uncompress(body_bytes)

    recv_ts = int(time.time() * 1000)

    rsp = OverField_pb2.PlayerPingRsp()
    rsp.ParseFromString(body_bytes)

    rtt = recv_ts - rsp.server_time_ms
    print(f"seq={seq} RTT: {rtt} ms")

    seq += 1
    # time.sleep(1)
