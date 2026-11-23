from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GetLifeSkillReq, GetLifeSkillRsp, StatusCode

import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.GetLifeSkillReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetLifeSkillReq()
        req.ParseFromString(data)

        rsp = GetLifeSkillRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.life_type = req.life_type
        # 纺织(5)无生活技能学习表, 返回 Spin.spin_spell 被动技能树
        if req.life_type == 5:
            for sp in res.get("Spin", {}).get("spin_spell", {}).get("datas", []):
                for it in sp.get("spin_spell_items", ()) or ():
                    sk = rsp.skill_info.add()
                    sk.skill_id = sp["i_d"]
                    sk.lv = int(it.get("level", 1))
            session.send(MsgId.GetLifeSkillRsp, rsp, packet_id)  # 1395,1396
            return
        skills = db.get_life_skills(session.player_id, req.life_type)
        for skill_id, (lv, start_time) in skills.items():
            skill = rsp.skill_info.add()
            skill.skill_id = skill_id
            skill.lv = lv
            skill.start_study_time = start_time
        session.send(MsgId.GetLifeSkillRsp, rsp, packet_id)  # 1395,1396
