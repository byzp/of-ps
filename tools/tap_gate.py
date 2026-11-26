#!/usr/bin/env python3
"""Gate tap: TCP relay 25566 -> 25567, decodes Open Space frames.

Frame layout (verified against the real client):
    [u16 BE headLen][PacketHead protobuf][body protobuf]

Writes one JSON line per frame to logs/packets_YYYYMMDD_HHMMSS.jsonl with
direction, msg id/name, sizes, packet_id, hex and decoded protobuf text.
Run from the of-ps folder so that `proto.net_pb2` is importable.
"""
import argparse
import json
import os
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from proto import net_pb2
    MSGS = net_pb2.DESCRIPTOR.message_types_by_name
except Exception as exc:  # pragma: no cover
    print("[tap] cannot import net_pb2:", exc)
    MSGS = {}

try:
    from network.msg_id import MsgId
    NAME_BY_ID = {v: k for k, v in vars(MsgId).items() if isinstance(v, int)}
except Exception:
    NAME_BY_ID = {}

try:
    from google.protobuf.text_format import MessageToString
except Exception:
    MessageToString = None

try:
    from google.protobuf import message_factory
except Exception:
    message_factory = None

_CLASS_CACHE = {}


def _class_for(desc):
    """Descriptor -> generated message class (protobuf >=4 returns Descriptor)."""
    key = desc.full_name
    cls = _CLASS_CACHE.get(key)
    if cls is None:
        if message_factory is not None and hasattr(message_factory, "GetMessageClass"):
            cls = message_factory.GetMessageClass(desc)
        else:
            cls = message_factory.MessageFactory().GetPrototype(desc)
        _CLASS_CACHE[key] = cls
    return cls


def decode_head(buf):
    """Minimal PacketHead parser: returns dict of known fields."""
    head = {}
    pos = 0
    n = len(buf)
    while pos < n:
        key = buf[pos]
        pos += 1
        field, wire = key >> 3, key & 7
        if field == 0:
            break
        if wire == 0:
            shift = 0
            val = 0
            while pos < n:
                b = buf[pos]
                pos += 1
                val |= (b & 0x7F) << shift
                if not b & 0x80:
                    break
                shift += 7
            if field in (2, 3, 4, 5, 6):
                head[field] = val
        elif wire == 2:
            if pos >= n:
                break
            shift = 0
            ln = 0
            while pos < n:
                b = buf[pos]
                pos += 1
                ln |= (b & 0x7F) << shift
                if not b & 0x80:
                    break
                shift += 7
            pos += ln
        elif wire == 5:
            pos += 4
        elif wire == 1:
            pos += 8
    return {
        "packet_id": head.get(1, 0),
        "msg_id": head.get(2, 0),
        "flag": head.get(3, 0),
        "body_len": head.get(4, 0),
        "total_pack": head.get(5, 0),
        "seq_id": head.get(6, 0),
    }


def decode_body(msg_id, body):
    name = NAME_BY_ID.get(msg_id)
    if not name or not MSGS:
        return name, None
    desc = MSGS.get(name)
    if desc is None:
        for cand, cand_desc in MSGS.items():
            if cand.lower() == name.lower():
                desc, name = cand_desc, cand
                break
    if desc is None:
        return name, None
    try:
        cls = _class_for(desc)
        msg = cls()
        msg.ParseFromString(body)
        return name, (MessageToString(msg, as_one_line=False) if MessageToString else str(msg))
    except Exception as exc:
        return name, "<decode failed: %s>" % exc


def pump(src, dst, log, tag, lock):
    buf = b""
    while True:
        try:
            chunk = src.recv(65536)
        except OSError:
            break
        if not chunk:
            break
        try:
            dst.sendall(chunk)
        except OSError:
            break
        buf += chunk
        while len(buf) >= 2:
            hlen = struct.unpack(">H", buf[:2])[0]
            if hlen == 0 or hlen > 512:
                buf = buf[1:]
                continue
            if len(buf) < 2 + hlen:
                break
            head_raw = buf[2:2 + hlen]
            head = decode_head(head_raw)
            blen = head.get("body_len", 0)
            if len(buf) < 2 + hlen + blen:
                break
            body = buf[2 + hlen:2 + hlen + blen]
            buf = buf[2 + hlen + blen:]
            name, text = decode_body(head["msg_id"], body)
            rec = {
                "t": round(time.time(), 3),
                "dir": tag,
                "msg_id": head["msg_id"],
                "name": name or str(head["msg_id"]),
                "packet_id": head["packet_id"],
                "flag": head["flag"],
                "seq": head["seq_id"],
                "body_len": blen,
                "head_hex": head_raw.hex(),
                "body_hex": body.hex(),
                "body_text": text,
            }
            with lock:
                log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log.flush()


def serve_conn(cli, target, log, lock):
    try:
        srv = socket.create_connection(target, timeout=5)
    except OSError as exc:
        print("[tap] upstream connect failed:", exc)
        cli.close()
        return
    t1 = threading.Thread(target=pump, args=(cli, srv, log, "C->S", lock), daemon=True)
    t2 = threading.Thread(target=pump, args=(srv, cli, log, "S->C", lock), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    for s in (cli, srv):
        try:
            s.close()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=25566)
    ap.add_argument("--target-port", type=int, default=25567)
    ap.add_argument("--target-host", default="127.0.0.1")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    logdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(logdir, exist_ok=True)
    logpath = args.log or os.path.join(logdir, "packets_%s.jsonl" % time.strftime("%Y%m%d_%H%M%S"))
    log = open(logpath, "a", encoding="utf-8")
    lock = threading.Lock()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", args.listen))
    s.listen(16)
    print("[tap] listening %d -> %s:%d" % (args.listen, args.target_host, args.target_port))
    print("[tap] logging to %s" % logpath)
    while True:
        try:
            cli, addr = s.accept()
        except KeyboardInterrupt:
            break
        print("[tap] conn from", addr)
        threading.Thread(
            target=serve_conn,
            args=(cli, (args.target_host, args.target_port), log, lock),
            daemon=True,
        ).start()


if __name__ == "__main__":
    main()
