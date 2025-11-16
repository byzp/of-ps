import logging
import struct
import socket
from io import BytesIO
from google.protobuf.message import Message
import snappy

from proto import OverField_pb2
from network.packet_factory import PacketFactory

logger = logging.getLogger(__name__)


class GameSession:
    HEADER_LENGTH = 2
    user_id = None
    player_name = None
    scene_id = 1
    channel_id = 1
    chat_channel_id = 1
    seq_id = 1
    avatar_id = 41101  # head
    badge_id = 0

    def __init__(self, client_socket: socket.socket, address: str):
        self.socket = client_socket
        self.address = address
        self.buffer = BytesIO()
        self.running = True
        self.logged_in = False

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
            self.running = False
            logger.info(f"Socket closed: {self.address}")

    def process_buffer(self):
        """Process buffered data"""
        data = self.buffer.getvalue()

        while len(data) >= self.HEADER_LENGTH:
            # Read header length
            header_len = struct.unpack(">H", data[: self.HEADER_LENGTH])[0]

            if len(data) < self.HEADER_LENGTH + header_len:
                break

            try:
                # Parse packet header
                packet_head = OverField_pb2.PacketHead()
                packet_head.ParseFromString(
                    data[self.HEADER_LENGTH : self.HEADER_LENGTH + header_len]
                )

                total_length = self.HEADER_LENGTH + header_len + packet_head.body_len

                if len(data) < total_length:
                    break

                # Extract body data
                body_data = data[self.HEADER_LENGTH + header_len : total_length]
                body_data = self._process_body(packet_head.flag, body_data)

                logger.debug(f"Received message: {packet_head.msg_id}")
                PacketFactory.process_packet(
                    packet_head.msg_id, body_data, packet_head.packet_id, self
                )

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

    def send(self, cmd_id: int, message: Message, sync: bool, packet_id: int):
        """Send protobuf message to client"""
        # logger.info(f"Sending message: {cmd_id}")

        body_data = message.SerializeToString()

        packet_head = OverField_pb2.PacketHead()
        packet_head.msg_id = cmd_id

        if packet_id != 0:
            packet_head.packet_id = packet_id

        if len(body_data) > 1200:
            packet_head.flag = 1
            body_data = snappy.compress(body_data)
        else:
            packet_head.flag = 0
        packet_head.body_len = len(body_data)

        if sync:
            packet_head.seq_id = 0
        else:
            packet_head.seq_id = self.seq_id
            self.seq_id += 1
            # logger.info(f"seq_id::{self.seq_id-1}")

        head_data = packet_head.SerializeToString()
        head_len = struct.pack(">H", len(head_data))

        try:
            self.socket.sendall(head_len + head_data + body_data)
        except Exception as e:
            print(e)
        logger.debug(f"Sending message: {cmd_id}")

    def sbin(self, cmd_id: int, path: str, sync: bool, packet_id: int):
        """Send protobuf message to client"""
        # logger.info(f"Sending bin message: {cmd_id}")

        with open(path, "rb") as f:
            body_data = f.read()

        packet_head = OverField_pb2.PacketHead()
        packet_head.msg_id = cmd_id

        if packet_id != 0:
            packet_head.packet_id = packet_id

        if len(body_data) > 1200:
            packet_head.flag = 1
            body_data = snappy.compress(body_data)
        else:
            packet_head.flag = 0
        packet_head.body_len = len(body_data)
        """
        global msg,stop,m2202
        if cmd_id==2202:
            head_data = packet_head.SerializeToString()
            head_len = struct.pack('>H', len(head_data))
            m2202=[cmd_id,[self, head_len + head_data + body_data]]
            return
        """

        if sync:
            packet_head.seq_id = 0
        else:
            packet_head.seq_id = self.seq_id
            self.seq_id += 1
            # logger.info(f"seq_id::{self.seq_id-1}")

        head_data = packet_head.SerializeToString()
        head_len = struct.pack(">H", len(head_data))

        """
        if cmd_id==1612:
            stop=1
        if stop==1 and cmd_id!=1862:
            msg.append([cmd_id,[self, head_len + head_data + body_data]])
            return
        
        if cmd_id==1862:
            print(">>>>>>>")
            for i in msg:
                i[1][0].socket.sendall(i[1][1])
                logger.info(f"Sending message: {i[0]}")
            self.socket.sendall(head_len + head_data + body_data)
            logger.info(f"Sending message: 1862")
            m2202[1][0].socket.sendall(m2202[1][1])
            logger.info(f"Sending message: 2202")
            stop=0
            return
        """
        try:
            self.socket.sendall(head_len + head_data + body_data)
        except Exception as e:
            print(e)
        logger.debug(f"Sending message: {cmd_id}")

    def close(self):
        """Close connection"""
        try:
            self.socket.close()
            self.running = False
        except Exception as e:
            logger.error(f"Failed to close connection: {e}")
