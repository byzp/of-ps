from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as PlayerMainDataRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as PackNotice_pb2

@packet_handler(CmdId.PlayerMainDataReq)
class GetPlayerMainDataHandler(PacketHandler):
    def handle(self, session, data: bytes):
        rsp = PlayerMainDataRsp_pb2.PlayerMainDataRsp()

        rsp.status = StatusCode_pb2.StatusCode_Ok
        rsp.player_id = 1234567
        rsp.player_name = "abc"
        #rsp.player_time_offset = 0  # int64
        #rsp.is_today_first_login = False
        rsp.unlock_functions.extend([100000009, 100000003, 100000021, 100000006,100000044, 100000031, 100000045, 100000046])
        rsp.level = 50
        rsp.exp = 1234
        rsp.head = 41101
        #rsp.sign = "hello world"
        rsp.phone_background = 2
        rsp.world_level = 5
        rsp.create_time = 1690000000
        rsp.scene_id = 1001
        rsp.channel_id = 5
        #rsp.reward_levels.extend([10, 20])
        #rsp.forbidden_infos.extend([])
        rsp.player_label = 1234567
        rsp.channel_label = 1234567
        rsp.month_card_over_due_time = 1744664399
        rsp.garden_likes_num = 16
        rsp.month_card_reward_days = 3
        #rsp.total_guarantee_dye_num = 0
        rsp.birthday = "1992-02-25"
        #rsp.is_hide_birthday = False

        session.send(CmdId.PlayerMainDataRsp, rsp)
        
        
        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_Ok
        rsp.temp_pack_max_size=30
        
        session.send(CmdId.PackNotice, rsp)

