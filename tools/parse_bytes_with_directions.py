#!/usr/bin/env python3
import struct
from io import BytesIO
import snappy
import OverField_pb2
import os


def parse_bytes_with_directions(data: bytes, directions):
    """
    data: bytes 全部拼接的数据流
    directions: 与 data 等长的列表，指明每个字节的流向字符串；或者为 None（未知）
    """
    stream = BytesIO(data)
    packet_num = 0
    total_len = len(data)

    while stream.tell() < total_len:
        try:
            pos = stream.tell()
            header_len_bytes = stream.read(2)
            if len(header_len_bytes) < 2:
                break
            header_len = struct.unpack(">H", header_len_bytes)[0]

            header_data = stream.read(header_len)
            if len(header_data) < header_len:
                print(
                    f"[WARN] 到达末尾但 header 长度不足：需要 {header_len}，得到 {len(header_data)}。停止。"
                )
                break

            packet_head = OverField_pb2.PacketHead()
            packet_head.ParseFromString(header_data)

            body_len = packet_head.body_len
            body_data = stream.read(body_len)
            if len(body_data) < body_len:
                print(
                    f"[WARN] 到达末尾但 body 长度不足：需要 {body_len}，得到 {len(body_data)}。停止。"
                )
                break

            # 判定方向：优先使用 header 起始字节对应的方向标签（更可靠）
            direction = "unknown"
            if directions is not None:
                if pos < len(directions):
                    direction = directions[pos]
                else:
                    direction = "unknown"

            # 解压（若需要）
            if getattr(packet_head, "flag", 0) == 1:
                try:
                    body_data = snappy.uncompress(body_data)
                except Exception as e:
                    print(f"[WARN] 第 {packet_num} 个包 Snappy 解压失败: {e}")

            # 清理 direction 字符串用于文件名
            dir_for_name = (
                direction.replace("->", "to").replace("/", "_").replace(":", "_")
            )
            out_filename = (
                f"packet_{packet_num}_{packet_head.msg_id}_{dir_for_name}_body.bin"
            )
            # 避免文件名过长或包含非法字符
            out_filename = "".join(c for c in out_filename if c.isalnum() or c in "._-")
            with open(out_filename, "wb") as fo:
                fo.write(body_data)

            print(f"\n=== 数据包 {packet_num} ===")
            # print(f"偏移: {pos}")
            print(f"消息ID: {packet_head.msg_id}")
            print(f"Body长度 (header): {packet_head.body_len}")
            print(f"压缩标志: {packet_head.flag}")
            print(f"流量方向: {direction}")
            print(f"Body已保存到: {out_filename}")

            packet_num += 1

        except Exception as e:
            print(f"[ERROR] 解析错误: {e}")
            break

    print(f"\n总共解析了 {packet_num} 个数据包")


def parse_from_tshark_tsv(tsv_path, server_port=11003):
    """
    读取由 tshark 输出的 TSV（每行：hex\tip.src\tip.dst\ttcp.srcport\ttcp.dstport）
    将每行的 hex bytes 按顺序拼接，并为这些字节标注方向（c->s 或 s->c），
    然后调用 parse_bytes_with_directions 进行解析。
    """
    if not os.path.exists(tsv_path):
        raise FileNotFoundError(f"{tsv_path} 未找到")

    data_chunks = []
    directions = []

    with open(tsv_path, "r", encoding="utf-8", errors="ignore") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            # tshark 输出通常是制表符分隔：hex \t ip.src \t ip.dst \t tcp.srcport \t tcp.dstport
            parts = line.split("\t")
            # 保护性解析：hex 可能在不同列（或有缺失字段）
            hex_field = parts[0] if len(parts) >= 1 else ""
            src = parts[1] if len(parts) >= 2 else ""
            dst = parts[2] if len(parts) >= 3 else ""
            sport = parts[3] if len(parts) >= 4 else ""
            dport = parts[4] if len(parts) >= 5 else ""

            hex_field = hex_field.strip()
            if hex_field == "":
                # 无 payload（或 tshark 未提取到），跳过
                continue
            # 某些 tshark 版本在 hex 中间有冒号或空格，去掉非十六进制字符
            # 仅保留 0-9 a-f A-F
            import re

            clean_hex = re.sub(r"[^0-9A-Fa-f]", "", hex_field)
            if clean_hex == "":
                continue

            try:
                chunk = bytes.fromhex(clean_hex)
            except Exception as e:
                print(f"[WARN] 第 {lineno} 行 hex 解析失败，跳过: {e}")
                continue

            # 判定方向：如果 dport == server_port 则认为 client->server；如果 sport == server_port 则 s->c
            dir_label = "unknown"
            try:
                if dport and int(dport) == int(server_port):
                    dir_label = "client->server"
                elif sport and int(sport) == int(server_port):
                    dir_label = "server->client"
                else:
                    dir_label = f"unknown({sport}->{dport})"
            except ValueError:
                dir_label = f"unknown({sport}->{dport})"

            data_chunks.append(chunk)
            directions.extend([dir_label] * len(chunk))

    data = b"".join(data_chunks)
    if len(data) == 0:
        print("[WARN] 从 tsv 未提取到任何 payload 数据。")
        return

    parse_bytes_with_directions(data, directions)


if __name__ == "__main__":
    # tshark -r of.pcapng -Y "tcp.port==11003" -T fields -e data.data -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport > payload_tshark.tsv
    parse_from_tshark_tsv("payload_tshark.tsv", server_port=11003)
