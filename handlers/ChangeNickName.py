from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ChangeNickNameReq,
    ChangeNickNameRsp,
    PackNotice,
    StatusCode,
    SceneActionType,
    ServerSceneSyncDataNotice,
)
from server.scene_data import up_scene_action

import utils.db as db
from utils import item_mgr
from utils.res_loader import res


@packet_handler(MsgId.ChangeNickNameReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeNickNameReq()
        req.ParseFromString(data)

        if not req.nick_name or not (len(req.nick_name.encode("utf-8")) <= 48):
            rsp = ChangeNickNameRsp()
            rsp.status = StatusCode.StatusCode_ILLEGAL_LEN
            session.send(MsgId.ChangeNickNameRsp, rsp, packet_id)
            return

        # 检查是否已存在相同的昵称
        if db.get_player_name_exists(req.nick_name):
            rsp = ChangeNickNameRsp()
            rsp.status = StatusCode.StatusCode_DUPLICATED_NAME
            session.send(MsgId.ChangeNickNameRsp, rsp, packet_id)
            return

        rsp = ChangeNickNameRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.nick_name = req.nick_name

        name_row = db.get_players_info(session.player_id, "player_name")
        first_name = not name_row or not name_row[0]
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        if not first_name and not item_mgr.consume_items(
            session.player_id,
            [(102, 10)],
            pack_notice=pack,
            session=session,
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            rsp.ClearField("nick_name")
            session.send(MsgId.ChangeNickNameRsp, rsp, packet_id)
            return

        session.player_name = req.nick_name

        # 存在birthday字段才更新数据库 修复不存在会覆盖为空的问题
        # 规范化为 %Y-%m-%d(make_ScenePlayer 依赖该格式判定生日), 非法格式忽略
        if req.birthday:
            birthday = None
            _parts = req.birthday.split("-")
            if all(p.isdigit() for p in _parts):
                if len(_parts) == 3:
                    _y, _m, _d = (int(_parts[0]), int(_parts[1]), int(_parts[2]))
                    if 1 <= _y <= 9999 and 1 <= _m <= 12:
                        _days = [
                            31,
                            28
                            + (
                                1
                                if _y % 4 == 0 and (_y % 100 != 0 or _y % 400 == 0)
                                else 0
                            ),
                            31,
                            30,
                            31,
                            30,
                            31,
                            31,
                            30,
                            31,
                            30,
                            31,
                        ][_m - 1]
                        if 1 <= _d <= _days:
                            birthday = req.birthday
                elif len(_parts) == 2:
                    _m, _d = int(_parts[0]), int(_parts[1])
                    if (
                        1 <= _m <= 12
                        and 1
                        <= _d
                        <= [
                            31,
                            29,
                            31,
                            30,
                            31,
                            30,
                            31,
                            31,
                            30,
                            31,
                            30,
                            31,
                        ][_m - 1]
                    ):
                        birthday = f"2000-{req.birthday}"
            if birthday:
                db.set_players_info(session.player_id, "birthday", birthday)
        db.set_players_info(session.player_id, "player_name", req.nick_name)

        # 改名冷却: RenamePunishTimeList 按累计改名次数取档(次数字段缺省按首档)
        _entry = None
        if (
            "GlobalConfig" in res
            and "config" in res["GlobalConfig"]
            and "datas" in res["GlobalConfig"]["config"]
        ):
            _entry = next(
                (
                    e
                    for e in res["GlobalConfig"]["config"]["datas"]
                    if e.get("key") == "RenamePunishTimeList"
                ),
                None,
            )
        if not first_name and _entry is not None:
            _raw = _entry.get("values")
            if isinstance(_raw, (list, tuple)):
                punish_list = [int(x) for x in _raw]
            else:
                punish_list = [int(x) for x in str(_raw).split(",")]
            if punish_list:
                rename_cnt = int(
                    db.get_kv(session.player_id, "profile", "rename_count", 0) or 0
                )
                db.set_kv(session.player_id, "profile", "rename_count", rename_cnt + 1)

        session.send(MsgId.ChangeNickNameRsp, rsp, packet_id)  # 修改昵称 1527 1528
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)

        # 发送场景同步通知
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        data_entry = notice.data.add()
        data_entry.player_id = session.player_id
        server_data_entry = data_entry.server_data.add()
        server_data_entry.action_type = SceneActionType.SceneActionType_UPDATE_NICKNAME

        session.scene_player.player_name = session.player_name
        server_data_entry.player.CopyFrom(session.scene_player)
        up_scene_action(session.scene_id, session.channel_id, notice)
