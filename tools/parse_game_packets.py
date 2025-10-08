#!/usr/bin/env python3
import struct
from io import BytesIO
import snappy
import OverField_pb2

def parse_game_packets(filename):
    with open(filename, 'rb') as f:
        data = f.read()
    
    stream = BytesIO(data)
    packet_num = 0
    
    while stream.tell() < len(data):
        try:
            # 读取header长度
            header_len_bytes = stream.read(2)
            if len(header_len_bytes) < 2:
                break
                
            header_len = struct.unpack('>H', header_len_bytes)[0]
            
            # 读取并解析PacketHead
            header_data = stream.read(header_len)
            packet_head = OverField_pb2.PacketHead()
            packet_head.ParseFromString(header_data)
            
            print(f"\n=== 数据包 {packet_num} ===")
            print(f"消息ID: {packet_head.msg_id}")
            print(f"Body长度: {packet_head.body_len}")
            print(f"压缩标志: {packet_head.flag}")
            
            # 读取body
            body_data = stream.read(packet_head.body_len)
            
            # 如果压缩则解压
            if packet_head.flag == 1:
                body_data = snappy.uncompress(body_data)
                #print("Body已解压")
            
            with open(f'packet_{packet_num}_body.bin', 'wb') as f:
                f.write(body_data)
            print(f"Body已保存到 packet_{packet_num}_body.bin")
            
            packet_num += 1
            
        except Exception as e:
            print(f"解析错误: {e}")
            break
    
    print(f"\n总共解析了 {packet_num} 个数据包")

# 使用
parse_game_packets('payload.bin')
#tshark -r of.pcapng -Y "tcp.port==11003" -T fields -e data.data > payload_hex.txt
#xxd -r -p payload_hex.txt > payload.bin