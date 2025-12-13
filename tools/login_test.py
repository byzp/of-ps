#!/usr/bin/env python3
import socket
import struct
import time
import threading
from proto import OverField_pb2
import requests
from urllib.parse import urlparse, parse_qs

HOST = "127.0.0.1"
PORT = 11033

# API login 地址
url = f"http://{HOST}:21000/api/login"
headers = {"Content-Type": "application/json"}

# 连接数（请根据需要修改）
NUM_CONN = 200

# 读取二进制包（所有线程共用只读数据）
with open("tmp/bin/packet_116_1203_clienttoserver_body.bin", "rb") as f:
    b1203 = f.read()


def recvall(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return buf
        buf += chunk
    return buf


def send_packet(sock, msg_id, req):
    body = req.SerializeToString()
    head = OverField_pb2.PacketHead()
    head.msg_id = msg_id
    head.flag = 0
    head.body_len = len(body)
    head.seq_id = 0
    head_data = head.SerializeToString()
    head_len = struct.pack(">H", len(head_data))
    sock.sendall(head_len + head_data + body)


def worker(conn_id):
    """
    每个连接的工作函数。
    conn_id 从 1 到 NUM_CONN，对应 username 值。
    """
    pl = {"username": str(conn_id), "password": "1"}
    try:
        # 建立 socket 连接（每个线程一个 socket）
        s = socket.socket()
        s.connect((HOST, PORT))
    except Exception as e:
        print(f"[conn {conn_id}] socket connect error: {e}")
        return

    try:
        # 第一步：调用登录接口获取 successUrl（和原脚本流程一致）
        try:
            response = requests.post(url, json=pl, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            success_url = data.get("successUrl", "")
            if not success_url:
                print(f"[conn {conn_id}] login response missing successUrl: {data}")
                s.close()
                return
            qs = parse_qs(urlparse(success_url).query)
            uid = qs.get("uid", [None])[0]
            user_token = qs.get("userToken", [None])[0]
            if not uid or not user_token:
                print(
                    f"[conn {conn_id}] failed to parse uid/userToken from successUrl: {success_url}"
                )
                s.close()
                return
        except Exception as e:
            print(f"[conn {conn_id}] HTTP login error: {e}")
            s.close()
            return

        # 发送 VerifyLoginTokenReq (msg_id 1001)
        req1 = OverField_pb2.VerifyLoginTokenReq()
        req1.sdk_uid = uid
        req1.login_token = user_token
        send_packet(s, 1001, req1)
        # 发送 PlayerLoginReq (msg_id 1003)
        req2 = OverField_pb2.PlayerLoginReq()
        send_packet(s, 1003, req2)
        # 发送 ChangeMusicalItemReq (msg_id 2671)
        req3 = OverField_pb2.ChangeMusicalItemReq()
        send_packet(s, 2671, req3)

        # 解析并准备 PlayerSceneRecordReq（1203）
        req4 = OverField_pb2.PlayerSceneRecordReq()
        req4.ParseFromString(b1203)

        # 持续发送 1203（与原脚本每秒一次）
        while True:
            send_packet(s, 1203, req4)
            time.sleep(0.2)

    except Exception as e:
        print(f"[conn {conn_id}] runtime error: {e}")
    finally:
        try:
            s.close()
        except:
            pass
        print(f"[conn {conn_id}] connection closed")


if __name__ == "__main__":
    threads = []
    for i in range(1, NUM_CONN + 1):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        threads.append(t)
        t.start()
        time.sleep(0.05)  # 小延迟避免瞬时并发过高（可删）

    # 主线程等待子线程（由于 worker 是无限循环发送，这里只是保活）
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("主线程收到中断，退出。")
