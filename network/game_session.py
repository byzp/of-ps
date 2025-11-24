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
    player_id = None
    player_name = None
    scene_id = 1
    channel_id = 1
    chat_channel_id = 1
    seq_id = 1
    avatar_id = 41101  # head
    badge_id = 0

    running = True
    verified = False
    logged_in = False

    def __init__(self, client_socket: socket.socket, address: str):
        self.socket = client_socket
        self.address = address
        self.buffer = BytesIO()
        self.scene_player = OverField_pb2.ScenePlayer()  # 玩家实体，在PlayerLogin初始化

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
            logger.debug(f"Connection error: {e}")
        finally:
            self.close()
            self.running = False
            logger.debug(f"Socket closed: {self.address}")

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

                # 阻止未授权访问
                if not self.verified and packet_head.msg_id not in [
                    1001,
                    1007,
                    2201,
                    2203,
                ]:
                    logger.warning(f"Unauthorized access: {self.address}")
                    self.close()
                    return

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

    def send(
        self,
        cmd_id: int,
        message: Message,
        packet_id: int,
        is_bin: bool = False,
    ):
        """Send protobuf message to client"""
        # logger.info(f"Sending message: {cmd_id}")
        if not is_bin:
            body_data = message.SerializeToString()
        else:
            body_data = message

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

        if cmd_id in [1002, 1004, 1006, 1008]:
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

    def sbin(self, cmd_id: int, path: str, packet_id: int):
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

        if cmd_id in [1002, 1004, 1006, 1008]:
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

    def close(self):
        """Close connection"""
        try:
            self.socket.close()
            self.running = False
        except Exception as e:
            logger.error(f"Failed to close connection: {e}")
