import logging
import struct
import socket
from io import BytesIO
from google.protobuf.message import Message
import snappy

from proto import OverField_pb2
from network.packet_factory import PacketFactory

logger = logging.getLogger(__name__)
import struct
import logging
from google.protobuf import json_format

class GameSession:
    HEADER_LENGTH = 2
    
    def __init__(self, client_socket: socket.socket):
        self.socket = client_socket
        self.buffer = BytesIO()
        self.running = True
    
    def run(self):
        """Main session loop"""
        try:
            while self.running:
                data = self.socket.recv(4096)
                if not data:
                    break
                
                self.buffer.write(data)
                self.process_buffer()
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            self.close()
    
    def process_buffer(self):
        """Process buffered data"""
        data = self.buffer.getvalue()
        
        while len(data) >= self.HEADER_LENGTH:
            # Read header length
            header_len = struct.unpack('>H', data[:self.HEADER_LENGTH])[0]
            
            if len(data) < self.HEADER_LENGTH + header_len:
                break
            
            try:
                # Parse packet header
                packet_head = OverField_pb2.PacketHead()
                packet_head.ParseFromString(
                    data[self.HEADER_LENGTH:self.HEADER_LENGTH + header_len]
                )
                
                total_length = self.HEADER_LENGTH + header_len + packet_head.body_len
                
                if len(data) < total_length:
                    break
                
                # Extract body data
                body_data = data[self.HEADER_LENGTH + header_len:total_length]
                body_data = self._process_body(packet_head.flag, body_data)
                
                logger.info(f"Received message: {packet_head.msg_id}")
                PacketFactory.process_packet(packet_head.msg_id, body_data, self)
                
                # Remove processed data
                data = data[total_length:]
                self.buffer = BytesIO()
                self.buffer.write(data)
                
            except Exception as e:
                logger.error(f"Packet processing failed: {e}")
                break
    
    def _process_body(self, flag: int, body: bytes) -> bytes:
        """Decompress body if needed"""
        if flag == 1:
            return snappy.uncompress(body)
        return body
    
    def send(self, cmd_id: int, message: Message):
        """Send protobuf message to client"""
        logger.info(f"Sending message: {cmd_id}")
        
        body_data = message.SerializeToString()
        
        packet_head = OverField_pb2.PacketHead()
        packet_head.msg_id = cmd_id
        packet_head.body_len = len(body_data)
        packet_head.flag = 0
        
        head_data = packet_head.SerializeToString()
        head_len = struct.pack('>H', len(head_data))
        print(str(message))
        self.socket.sendall(head_len + head_data + body_data)
    
    def close(self):
        """Close connection"""
        try:
            self.socket.close()
            self.running = False
        except Exception as e:
            logger.error(f"Failed to close connection: {e}")

