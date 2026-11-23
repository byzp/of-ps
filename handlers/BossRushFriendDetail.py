from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BossRushFriendDetailReq,
    BossRushFriendDetailRsp,
    BossRushInfo,
    StatusCode,
)

from utils import db
from utils.res_loader import res


@packet_handler(MsgId.BossRushFriendDetailReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushFriendDetailReq()
        req.ParseFromString(data)

        rsp = BossRushFriendDetailRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.player_id = req.player_id

        # 查看好友(或自己)的 BossRush 各赛季战绩详情
        target_id = req.player_id if req.player_id else session.player_id
        _tab = (
            res["BossRush"]["boss_rush_season"]["datas"]
            if isinstance(res.get("BossRush"), dict)
            and isinstance(res["BossRush"].get("boss_rush_season"), dict)
            else []
        )
        season_ids = (
            [s["i_d"] for s in _tab if isinstance(s, dict) and "i_d" in s]
            if isinstance(_tab, (list, tuple))
            else []
        )

        for season_id in season_ids:
            blob = db.get_boss_rush_info(target_id, season_id)
            if not blob:
                continue
            br = BossRushInfo()
            br.ParseFromString(blob)
            detail = rsp.details.add()
            detail.season_id = season_id
            detail.score = br.best_total_score
            detail.rank_ratio = br.total_rank_ratio
            for si in br.stage_infos:
                st = detail.stage.add()
                st.stage_index = si.stage_index
                st.best_score = si.best_score
                st.is_passed = si.is_passed
                for team in si.teams:  # 与 BossRushSeasonDetailStageTeam 同类型
                    st.teams.add().CopyFrom(team)

        session.send(MsgId.BossRushFriendDetailRsp, rsp, packet_id)  # 2713,2714
