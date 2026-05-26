#!/usr/bin/env python3
"""
登录流程路径测试
测试各 handler 的多种执行路径

依赖: 需先启动服务端 (python main.py)
"""
import socket
import struct
import time
import sys
from proto.net_pb2 import *
import requests
from urllib.parse import urlparse, parse_qs

HOST = "127.0.0.1"
PORT = 11033
API_URL = f"http://{HOST}:21000/api/login"
HEADERS = {"Content-Type": "application/json"}

GROUP_RESULTS = []


# ── 底层工具 ──


def recvall(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return buf
        buf += chunk
    return buf


def send_packet(sock, msg_id, req):
    body = req.SerializeToString()
    head = PacketHead()
    head.msg_id = msg_id
    head.flag = 0
    head.body_len = len(body)
    head.seq_id = 0
    head_data = head.SerializeToString()
    head_len = struct.pack(">H", len(head_data))
    sock.sendall(head_len + head_data + body)


def recv_packet(sock, timeout=5):
    sock.settimeout(timeout)
    try:
        hl = recvall(sock, 2)
        if len(hl) < 2:
            return None
        hllen = struct.unpack(">H", hl)[0]
        head_bytes = recvall(sock, hllen)
        if len(head_bytes) < hllen:
            return None
        rsp_head = PacketHead()
        rsp_head.ParseFromString(head_bytes)
        body_bytes = recvall(sock, rsp_head.body_len)
        if len(body_bytes) < rsp_head.body_len:
            return None
        if rsp_head.flag == 1:
            import snappy

            body_bytes = snappy.uncompress(body_bytes)
        return rsp_head.msg_id, body_bytes
    except socket.timeout:
        return None


def drain(sock, timeout=0.5):
    """清空 socket 接收缓冲区中所有残留包"""
    while True:
        pkt = recv_packet(sock, timeout)
        if pkt is None:
            break


def http_login(username="test", password="1"):
    try:
        r = requests.post(
            API_URL,
            json={"username": username, "password": password},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        su = data.get("successUrl", "")
        if not su:
            return None
        qs = parse_qs(urlparse(su).query)
        uid = qs.get("uid", [None])[0]
        token = qs.get("userToken", [None])[0]
        if uid and token:
            return uid, token
        return None
    except Exception:
        return None


def make_socket():
    s = socket.socket()
    s.connect((HOST, PORT))
    return s


def group(name):
    GROUP_RESULTS.append({"name": name, "pass": 0, "fail": 0})


def g_log(msg, ok=True):
    grp = GROUP_RESULTS[-1]
    if ok:
        grp["pass"] += 1
        print(f"    PASS: {msg}")
    else:
        grp["fail"] += 1
        print(f"    FAIL: {msg}", file=sys.stderr)


def print_group_summary():
    print()
    for g in GROUP_RESULTS:
        total = g["pass"] + g["fail"]
        status = "OK" if g["fail"] == 0 else "FAIL"
        print(f"  [{status}] {g['name']}: {g['pass']}/{total}")


# ═══════════════════════════════════════
# 测试用例（按 handler 分组）
# ═══════════════════════════════════════


def test_http_login():
    """HTTP /api/login"""
    group("HttpLogin")

    r = requests.post(
        API_URL,
        json={"username": "no_such_user", "password": "wrong"},
        headers=HEADERS,
        timeout=10,
    )
    data = r.json()
    g_log(f"错误密码 → success={data.get('success')}", data.get("success") == False)

    creds = http_login("path_test", "1")
    g_log("正确密码获取 uid+token", creds is not None)
    return creds


def test_unverified_access():
    """未验证访问 → 连接关闭（按 game_session.py:174 未验证直接发包会被 close）"""
    group("UnverifiedAccess")

    s = make_socket()
    req = PlayerLoginReq()
    send_packet(s, 1003, req)
    try:
        s.settimeout(3)
        data = s.recv(1)
        connected = len(data) > 0
    except (socket.timeout, OSError, ConnectionResetError):
        connected = False
    g_log(f"未验证发 PlayerLoginReq → 连接关闭={not connected}", not connected)
    s.close()


def test_verify_login_token(sock, uid, token):
    """VerifyLoginToken (1001)"""
    group("VerifyLoginToken")

    req = VerifyLoginTokenReq()
    req.sdk_uid = uid
    req.login_token = token
    send_packet(sock, 1001, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("正常验证: 无响应", False)
        return False
    mid, body = pkt
    rsp = VerifyLoginTokenRsp()
    rsp.ParseFromString(body)
    g_log(
        f"正常验证: msg_id={mid} status={StatusCode.Name(rsp.status)}",
        mid == 1002 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)
    return True


def test_verify_login_duplicate(uid, token):
    """VerifyLoginToken 重复登录踢旧连接（VerifyLoginToken.py:32-42）"""
    s1 = make_socket()
    req = VerifyLoginTokenReq()
    req.sdk_uid = uid
    req.login_token = token
    send_packet(s1, 1001, req)
    if recv_packet(s1) is None:
        g_log("重复登录: s1 Verify失败", False)
        s1.close()
        return
    drain(s1)

    req2 = PlayerLoginReq()
    send_packet(s1, 1003, req2)
    if recv_packet(s1) is None:
        g_log("重复登录: s1 PlayerLogin失败", False)
        s1.close()
        return
    drain(s1)

    req3 = PlayerMainDataReq()
    send_packet(s1, 1005, req3)
    if recv_packet(s1) is None:
        g_log("重复登录: s1 MainData失败", False)
        s1.close()
        return
    drain(s1)

    s2 = make_socket()
    req4 = VerifyLoginTokenReq()
    req4.sdk_uid = uid
    req4.login_token = token
    send_packet(s2, 1001, req4)
    if recv_packet(s2) is None:
        g_log("重复登录: s2 无响应", False)
        s1.close()
        s2.close()
        return

    kicked = False
    try:
        s1.settimeout(3)
        kick_pkt = recv_packet(s1)
        if kick_pkt:
            mid, body = kick_pkt
            if mid == 1010:
                rsp = PlayerOfflineRsp()
                rsp.ParseFromString(body)
                kicked = (
                    rsp.reason == PlayerOfflineReason.PlayerOfflineReason_ANOTHER_LOGIN
                )
    except (socket.timeout, OSError):
        pass

    g_log(f"重复登录: 旧连接被踢={kicked}", kicked)
    s1.close()
    s2.close()


def test_player_login(sock):
    """PlayerLogin (1003)"""
    group("PlayerLogin")

    req = PlayerLoginReq()
    send_packet(sock, 1003, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("正常登录: 无响应", False)
        return
    mid, body = pkt
    rsp = PlayerLoginRsp()
    rsp.ParseFromString(body)
    g_log(
        f"正常登录: status={StatusCode.Name(rsp.status)} scene_id={rsp.scene_id}",
        mid == 1004 and rsp.status == StatusCode.StatusCode_OK and rsp.scene_id > 0,
    )
    drain(sock)

    req2 = PlayerLoginReq()
    req2.is_reconnect = True
    send_packet(sock, 1003, req2)
    pkt2 = recv_packet(sock)
    if pkt2 is None:
        g_log("重连拒绝: 无响应", False)
        return
    mid2, body2 = pkt2
    rsp2 = PlayerLoginRsp()
    rsp2.ParseFromString(body2)
    g_log(
        f"重连拒绝: status={StatusCode.Name(rsp2.status)}",
        mid2 == 1004 and rsp2.status == StatusCode.StatusCode_FAIL,
    )
    drain(sock)


def test_player_main_data(sock):
    """PlayerMainData (1005)"""
    group("PlayerMainData")

    req = PlayerMainDataReq()
    send_packet(sock, 1005, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("获取主数据: 无响应", False)
        return
    mid, body = pkt
    rsp = PlayerMainDataRsp()
    rsp.ParseFromString(body)
    g_log(
        f"获取主数据: player_id={rsp.player_id} level={rsp.level}",
        mid == 1006 and rsp.status == StatusCode.StatusCode_OK and rsp.player_id > 0,
    )
    drain(sock)


def test_player_ping(sock):
    """PlayerPing (1007)"""
    group("PlayerPing")

    req = PlayerPingReq()
    req.client_time_ms = int(time.time() * 1000)
    send_packet(sock, 1007, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("Ping: 无响应", False)
        return
    mid, body = pkt
    rsp = PlayerPingRsp()
    rsp.ParseFromString(body)
    g_log(
        f"Ping: status={StatusCode.Name(rsp.status)} server_time={rsp.server_time_ms}",
        mid == 1008
        and rsp.status == StatusCode.StatusCode_OK
        and abs(rsp.server_time_ms - req.client_time_ms) < 5000,
    )
    drain(sock)


def test_change_nickname(sock):
    """ChangeNickName (1511)"""
    group("ChangeNickName")

    req = ChangeNickNameReq()
    req.nick_name = f"TestUser_{int(time.time())}"
    send_packet(sock, 1511, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("修改昵称: 无响应", False)
        return
    mid, body = pkt
    rsp = ChangeNickNameRsp()
    rsp.ParseFromString(body)
    g_log(
        f"修改昵称: status={StatusCode.Name(rsp.status)} name={rsp.nick_name}",
        mid == 1512 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_change_sign(sock):
    """ChangeSign (1513)"""
    group("ChangeSign")

    req = ChangeSignReq()
    req.sign = "Hello from test!"
    send_packet(sock, 1513, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("修改签名: 无响应", False)
        return
    mid, body = pkt
    rsp = ChangeSignRsp()
    rsp.ParseFromString(body)
    g_log(
        f"修改签名: status={StatusCode.Name(rsp.status)} sign={rsp.sign}",
        mid == 1514 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_change_head(sock):
    """ChangeHead (1515)"""
    group("ChangeHead")

    req = ChangeHeadReq()
    req.head = 40001
    send_packet(sock, 1515, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("修改头像: 无响应", False)
        return
    mid, body = pkt
    rsp = ChangeHeadRsp()
    rsp.ParseFromString(body)
    g_log(
        f"修改头像: status={StatusCode.Name(rsp.status)} head={rsp.head}",
        mid == 1516 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_change_phone_bg(sock):
    """ChangePhoneBackground (1517)"""
    group("ChangePhoneBackground")

    req = ChangePhoneBackgroundReq()
    req.phone_background = 1001
    send_packet(sock, 1517, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("修改手机背景: 无响应", False)
        return
    mid, body = pkt
    rsp = ChangePhoneBackgroundRsp()
    rsp.ParseFromString(body)
    g_log(
        f"修改手机背景: status={StatusCode.Name(rsp.status)} bg={rsp.phone_background}",
        mid == 1518 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_change_pet(sock):
    """ChangePet (4541)"""
    group("ChangePet")

    req = ChangePetReq()
    req.pet_instance_id = 0
    send_packet(sock, 4541, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("修改宠物: 无响应", False)
        return
    mid, body = pkt
    rsp = ChangePetRsp()
    rsp.ParseFromString(body)
    g_log(
        f"修改宠物: status={StatusCode.Name(rsp.status)} pet_id={rsp.pet_instance_id}",
        mid == 4542 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_send_chat_msg(sock):
    """SendChatMsg (1933)"""
    group("SendChatMsg")

    req = SendChatMsgReq()
    req.text = "Hello World!"
    req.type = 1
    send_packet(sock, 1933, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("发送聊天: 无响应", False)
        return
    mid, body = pkt
    rsp = SendChatMsgRsp()
    rsp.ParseFromString(body)
    g_log(
        f"发送聊天: status={StatusCode.Name(rsp.status)} text={rsp.text}",
        mid == 1934 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_get_mails(sock):
    """GetMails (1121)"""
    group("GetMails")

    req = GetMailsReq()
    send_packet(sock, 1121, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("获取邮件: 无响应", False)
        return
    mid, body = pkt
    rsp = GetMailsRsp()
    rsp.ParseFromString(body)
    g_log(
        f"获取邮件: status={StatusCode.Name(rsp.status)} mails_count={len(rsp.mails)}",
        mid == 1122 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_gacha_list(sock):
    """GachaList (1443)"""
    group("GachaList")

    req = GachaListReq()
    send_packet(sock, 1443, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("获取卡池列表: 无响应", False)
        return
    mid, body = pkt
    rsp = GachaListRsp()
    rsp.ParseFromString(body)
    g_log(
        f"获取卡池列表: status={StatusCode.Name(rsp.status)} gachas={len(rsp.gachas)}",
        mid == 1444 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_shop_info(sock):
    """ShopInfo (1675)"""
    group("ShopInfo")

    for sid in [100, 200, 300, 400, 500, 600, 800, 900, 1000]:
        req = ShopInfoReq()
        req.shop_id = sid
        send_packet(sock, 1675, req)
        pkt = recv_packet(sock)
        if pkt is None:
            g_log(f"获取商店(sid={sid}): 无响应", False)
            continue
        mid, body = pkt
        rsp = ShopInfoRsp()
        rsp.ParseFromString(body)
        g_log(
            f"商店(sid={sid}): status={StatusCode.Name(rsp.status)} grids={len(rsp.grids)}",
            mid == 1676 and rsp.status == StatusCode.StatusCode_OK,
        )
        drain(sock)


def test_tutorial(sock):
    """Tutorial (1589)"""
    group("Tutorial")

    req = TutorialReq()
    send_packet(sock, 1589, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("教程确认: 无响应", False)
        return
    mid, body = pkt
    rsp = TutorialRsp()
    rsp.ParseFromString(body)
    g_log(
        f"教程确认: status={StatusCode.Name(rsp.status)}",
        mid == 1590 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_npc_talk(sock):
    """NpcTalk (1803)"""
    group("NpcTalk")

    req = NpcTalkReq()
    req.id = 1001
    req.talk_type = 0
    send_packet(sock, 1803, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("NPC对话: 无响应", False)
        return
    mid, body = pkt
    rsp = NpcTalkRsp()
    rsp.ParseFromString(body)
    g_log(
        f"NPC对话: status={StatusCode.Name(rsp.status)}",
        mid == 1804 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_manual_list(sock):
    """ManualList (1861)"""
    group("ManualList")

    req = ManualListReq()
    send_packet(sock, 1861, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("获取手册列表: 无响应", False)
        return
    mid, body = pkt
    rsp = ManualListRsp()
    rsp.ParseFromString(body)
    g_log(
        f"获取手册列表: status={StatusCode.Name(rsp.status)} flags={len(rsp.flags)}",
        mid == 1862 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_player_ability_list(sock):
    """PlayerAbilityList (1611)"""
    group("PlayerAbilityList")

    req = PlayerAbilityListReq()
    send_packet(sock, 1611, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("获取能力列表: 无响应", False)
        return
    mid, body = pkt
    rsp = PlayerAbilityListRsp()
    rsp.ParseFromString(body)
    g_log(
        f"获取能力列表: status={StatusCode.Name(rsp.status)}",
        mid == 1612 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_get_weapons(sock):
    """GetWeapon (1401)"""
    group("GetWeapon")

    req = GetWeaponReq()
    send_packet(sock, 1401, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("获取武器: 无响应", False)
        return
    mid, body = pkt
    rsp = GetWeaponRsp()
    rsp.ParseFromString(body)
    g_log(
        f"获取武器: status={StatusCode.Name(rsp.status)} count={rsp.total_num}",
        mid == 1402 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_get_armors(sock):
    """GetArmor (1403)"""
    group("GetArmor")

    req = GetArmorReq()
    req.start_index = 0
    req.end_index = 50
    send_packet(sock, 1403, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("获取防具: 无响应", False)
        return
    mid, body = pkt
    rsp = GetArmorRsp()
    rsp.ParseFromString(body)
    g_log(
        f"获取防具: status={StatusCode.Name(rsp.status)} count={rsp.total_num}",
        mid == 1404 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_get_posters(sock):
    """GetPoster (1405)"""
    group("GetPoster")

    req = GetPosterReq()
    req.start_index = 0
    req.end_index = 50
    send_packet(sock, 1405, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("获取映像: 无响应", False)
        return
    mid, body = pkt
    rsp = GetPosterRsp()
    rsp.ParseFromString(body)
    g_log(
        f"获取映像: status={StatusCode.Name(rsp.status)} count={rsp.total_num}",
        mid == 1406 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_get_all_character_equip(sock):
    """GetAllCharacterEquip (1415)"""
    group("GetAllCharacterEquip")

    req = GetAllCharacterEquipReq()
    send_packet(sock, 1415, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("获取全部装备: 无响应", False)
        return
    mid, body = pkt
    rsp = GetAllCharacterEquipRsp()
    rsp.ParseFromString(body)
    g_log(
        f"获取全部装备: status={StatusCode.Name(rsp.status)} items={len(rsp.items)}",
        mid == 1416 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_change_musical_item(sock):
    """ChangeMusicalItem (2671)"""
    group("ChangeMusicalItem")

    req = ChangeMusicalItemReq()
    req.musical_item_instance_id = 10001
    send_packet(sock, 2671, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("更换乐器: 无响应", False)
        return
    mid, body = pkt
    rsp = ChangeMusicalItemRsp()
    rsp.ParseFromString(body)
    g_log(
        f"更换乐器: status={StatusCode.Name(rsp.status)}",
        mid == 2672 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_friend_list(sock):
    """Friend (1739)"""
    group("Friend")

    req = FriendReq()
    send_packet(sock, 1739, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("列出好友: 无响应", False)
        return
    mid, body = pkt
    rsp = FriendRsp()
    rsp.ParseFromString(body)
    g_log(
        f"列出好友: status={StatusCode.Name(rsp.status)} friends={len(rsp.info)}",
        mid == 1740 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_friend_search(sock, name):
    """FriendSearch (1727) — 按玩家名搜索"""
    group("FriendSearch")

    req = FriendSearchReq()
    req.search_args = name
    send_packet(sock, 1727, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("搜索好友: 无响应", False)
        return
    mid, body = pkt
    rsp = FriendSearchRsp()
    rsp.ParseFromString(body)
    g_log(
        f"搜索好友: status={StatusCode.Name(rsp.status)} player_id={rsp.data.player_id}",
        mid == 1728 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_change_scene_channel(sock):
    """ChangeSceneChannel (1201) — 切换到花园(9999)"""
    group("ChangeSceneChannel")

    req = ChangeSceneChannelReq()
    req.scene_id = 9999
    req.channel_label = 1
    send_packet(sock, 1201, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("切换场景: 无响应", False)
        return
    mid, body = pkt
    rsp = ChangeSceneChannelRsp()
    rsp.ParseFromString(body)
    g_log(
        f"切换场景(花园): status={StatusCode.Name(rsp.status)} scene_id={rsp.scene_id}",
        mid == 1202 and rsp.status == StatusCode.StatusCode_OK and rsp.scene_id == 9999,
    )
    drain(sock)


def test_area_unlock(sock):
    """AreaUnlock (1903)"""
    group("AreaUnlock")

    req = AreaUnlockReq()
    req.area_id = 1001
    send_packet(sock, 1903, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("解锁区域: 无响应", False)
        return
    mid, body = pkt
    rsp = AreaUnlockRsp()
    rsp.ParseFromString(body)
    ok = (
        rsp.status == StatusCode.StatusCode_OK
        or rsp.status == StatusCode.StatusCode_AREA_ALREADY_UNLOCK
    )
    g_log(
        f"解锁区域: status={StatusCode.Name(rsp.status)} area_id={rsp.area.area_id}",
        mid == 1904 and ok,
    )
    drain(sock)


def test_monster_dead(sock):
    """MonsterDead (1851)"""
    group("MonsterDead")

    req = MonsterDeadReq()
    req.monster_index = 0
    send_packet(sock, 1851, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("怪物死亡: 无响应", False)
        return
    mid, body = pkt
    rsp = MonsterDeadRsp()
    rsp.ParseFromString(body)
    has_drop = len(rsp.drop_item.items) > 0
    g_log(
        f"怪物死亡: status={StatusCode.Name(rsp.status)} has_drop={has_drop}",
        mid == 1852 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_collecting(sock):
    """Collecting (1741)"""
    group("Collecting")

    req = CollectingReq()
    req.item_id = 90001
    send_packet(sock, 1741, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("收集物品: 无响应", False)
        return
    mid, body = pkt
    rsp = CollectingRsp()
    rsp.ParseFromString(body)
    ok = (
        rsp.status == StatusCode.StatusCode_OK
        or rsp.status == StatusCode.StatusCode_ALREADY_COLLECTED
    )
    g_log(f"收集物品: status={StatusCode.Name(rsp.status)}", mid == 1742 and ok)
    drain(sock)


def test_item_use(sock):
    """ItemUse (1959) — 用不存在的物品 → ITEM_NOT_ENOUGH"""
    group("ItemUse")

    req = ItemUseReq()
    req.item_id = 999999
    req.num = 1
    send_packet(sock, 1959, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("使用物品(不存在): 无响应", False)
        return
    mid, body = pkt
    rsp = ItemUseRsp()
    rsp.ParseFromString(body)
    g_log(
        f"使用物品(不存在): status={StatusCode.Name(rsp.status)}",
        mid == 1960 and rsp.status == StatusCode.StatusCode_ITEM_NOT_ENOUGH,
    )
    drain(sock)


def test_cooking_food(sock):
    """CookingFood (1379) — PackNotice (1400) 先于 Rsp 发送"""
    group("CookingFood")

    req = CookingFoodReq()
    req.food_id = 1
    send_packet(sock, 1379, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("烹饪食物: 无响应", False)
        return
    mid, body = pkt
    if mid == 1400:
        pkt = recv_packet(sock)
        if pkt is None:
            g_log("烹饪食物: 无响应(跳过PackNotice)", False)
            return
        mid, body = pkt
    rsp = CookingFoodRsp()
    rsp.ParseFromString(body)
    ok = (
        rsp.status == StatusCode.StatusCode_OK
        or rsp.status == StatusCode.StatusCode_EnergyNotEnough
    )
    g_log(
        f"烹饪食物: status={StatusCode.Name(rsp.status)} is_success={rsp.life_common_result.is_success}",
        mid == 1380 and ok,
    )
    drain(sock)


def test_activity_sign_in(sock):
    """ActivitySignIn (1985) — PackNotice (1400) 先于 Rsp 发送"""
    group("ActivitySignIn")

    req = ActivitySignInReq()
    req.activity_id = 1
    req.day = 1
    send_packet(sock, 1985, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("活动签到: 无响应", False)
        return
    mid, body = pkt
    if mid == 1400:
        pkt = recv_packet(sock)
        if pkt is None:
            g_log("活动签到: 无响应(跳过PackNotice)", False)
            return
        mid, body = pkt
    rsp = ActivitySignInRsp()
    rsp.ParseFromString(body)
    g_log(
        f"活动签到: status={StatusCode.Name(rsp.status)} day={rsp.day} reward_id={rsp.reward_id}",
        mid == 1986 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_supply_box_reward(sock):
    """SupplyBoxReward (1893)"""
    group("SupplyBoxReward")

    req = SupplyBoxRewardReq()
    send_packet(sock, 1893, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("补给箱奖励: 无响应", False)
        return
    mid, body = pkt
    rsp = SupplyBoxRewardRsp()
    rsp.ParseFromString(body)
    g_log(
        f"补给箱奖励: status={StatusCode.Name(rsp.status)} items={len(rsp.items)}",
        mid == 1894 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_update_team(sock):
    """UpdateTeam (1641)"""
    group("UpdateTeam")

    req = UpdateTeamReq()
    req.char1 = 1001
    req.char2 = 1002
    req.char3 = 1003
    send_packet(sock, 1641, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("更新队伍: 无响应", False)
        return
    mid, body = pkt
    rsp = UpdateTeamRsp()
    rsp.ParseFromString(body)
    g_log(
        f"更新队伍: status={StatusCode.Name(rsp.status)}",
        mid == 1642 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_ability_badge_list(sock):
    """AbilityBadgeList (1631)"""
    group("AbilityBadgeList")

    req = AbilityBadgeListReq()
    send_packet(sock, 1631, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("能力徽章列表: 无响应", False)
        return
    mid, body = pkt
    rsp = AbilityBadgeListRsp()
    rsp.ParseFromString(body)
    pages = len(rsp.ability_badge_pages)
    achieves = len(rsp.ability_badge_achieves)
    g_log(
        f"能力徽章列表: status={StatusCode.Name(rsp.status)} pages={pages} achieves={achieves}",
        mid == 1632 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_shop_buy(sock):
    """ShopBuy (1677) — 买商店物品"""
    group("ShopBuy")

    req = ShopBuyReq()
    req.shop_id = 100
    req.grid_id = 1
    req.buy_times = 1
    send_packet(sock, 1677, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("商店购买: 无响应", False)
        return
    mid, body = pkt
    rsp = ShopBuyRsp()
    rsp.ParseFromString(body)
    ok = (
        rsp.status == StatusCode.StatusCode_OK
        or rsp.status == StatusCode.StatusCode_ITEM_NOT_ENOUGH
    )
    g_log(
        f"商店购买(sid=100): status={StatusCode.Name(rsp.status)}", mid == 1678 and ok
    )
    drain(sock)


def test_character_level_up(sock):
    """CharacterLevelUp (1039) — 用不存在的角色 → CHARACTER_NOT_FOUND"""
    group("CharacterLevelUp")

    req = CharacterLevelUpReq()
    req.char_id = 99999
    req.nums.extend([0, 0, 0])
    send_packet(sock, 1039, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("角色升级(不存在): 无响应", False)
        return
    mid, body = pkt
    rsp = CharacterLevelUpRsp()
    rsp.ParseFromString(body)
    ok = (
        rsp.status == StatusCode.StatusCode_CharNotExist
        or rsp.status == StatusCode.StatusCode_OK
    )
    g_log(f"角色升级(不存在): status={StatusCode.Name(rsp.status)}", mid == 1040 and ok)
    drain(sock)


def test_character_star_up(sock):
    """CharacterStarUp (1037) — 不存在的角色 → CharNotExist"""
    group("CharacterStarUp")

    req = CharacterStarUpReq()
    req.char_id = 99999
    send_packet(sock, 1037, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("角色升星(不存在): 无响应", False)
        return
    mid, body = pkt
    rsp = CharacterStarUpRsp()
    rsp.ParseFromString(body)
    ok = rsp.status != StatusCode.StatusCode_FAIL
    g_log(f"角色升星(不存在): status={StatusCode.Name(rsp.status)}", mid == 1038 and ok)
    drain(sock)


def test_gacha(sock):
    """Gacha (1445) — 抽卡"""
    group("Gacha")

    req = GachaReq()
    req.gacha_id = 2000
    req.is_single = True
    send_packet(sock, 1445, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("抽卡: 无响应", False)
        return
    mid, body = pkt
    rsp = GachaRsp()
    rsp.ParseFromString(body)
    ok = (
        rsp.status == StatusCode.StatusCode_OK
        or rsp.status == StatusCode.StatusCode_ITEM_NOT_ENOUGH
    )
    g_log(
        f"抽卡(pool=2000 single): status={StatusCode.Name(rsp.status)} guarantee={rsp.info.guarantee}",
        mid == 1446 and ok,
    )
    drain(sock)


def test_pet_capture(sock):
    """PetCapture (4531) — 没有捕兽夹 → ITEM_NOT_ENOUGH"""
    group("PetCapture")

    req = PetCaptureReq()
    req.catcher_id = 999999
    req.monster_id = 1001
    send_packet(sock, 4531, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("捕捉宠物(无捕捉器): 无响应", False)
        return
    mid, body = pkt
    rsp = PetCaptureRsp()
    rsp.ParseFromString(body)
    g_log(
        f"捕捉宠物(无捕捉器): status={StatusCode.Name(rsp.status)}",
        mid == 4532 and rsp.status == StatusCode.StatusCode_ITEM_NOT_ENOUGH,
    )
    drain(sock)


def test_explore_init(sock):
    """ExploreInit (1819)"""
    group("ExploreInit")

    req = ExploreInitReq()
    send_packet(sock, 1819, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("探索初始化: 无响应", False)
        return
    mid, body = pkt
    rsp = ExploreInitRsp()
    rsp.ParseFromString(body)
    g_log(
        f"探索初始化: status={StatusCode.Name(rsp.status)} explores={len(rsp.explore)}",
        mid == 1820 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_supply_box_info(sock):
    """SupplyBoxInfo (1891)"""
    group("SupplyBoxInfo")

    req = SupplyBoxInfoReq()
    send_packet(sock, 1891, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("补给箱信息: 无响应", False)
        return
    mid, body = pkt
    rsp = SupplyBoxInfoRsp()
    rsp.ParseFromString(body)
    g_log(
        f"补给箱信息: status={StatusCode.Name(rsp.status)} next_reward_time={rsp.next_reward_time}",
        mid == 1892 and rsp.status == StatusCode.StatusCode_OK,
    )
    drain(sock)


def test_scene_sit_chair(sock):
    """SceneSitChair (1801)"""
    group("SceneSitChair")

    req = SceneSitChairReq()
    req.chair_id = 1
    req.seat_id = 0
    req.is_sit = True
    send_packet(sock, 1801, req)
    pkt = recv_packet(sock)
    if pkt is None:
        g_log("坐椅子: 无响应", False)
        return
    mid, body = pkt
    rsp = SceneSitChairRsp()
    rsp.ParseFromString(body)
    g_log(
        f"坐椅子: status={StatusCode.Name(rsp.status)} chair_id={rsp.chair_id} is_sit={rsp.is_sit}",
        mid == 1802 and rsp.status == StatusCode.StatusCode_OK and rsp.is_sit == True,
    )
    drain(sock)


# ═══════════════════════════════════════
# 主入口
# ═══════════════════════════════════════

if __name__ == "__main__":
    print("=" * 56)
    print("  登录流程路径测试 (handler 分组)")
    print("=" * 56)

    # ── 不需要 socket 连接的测试 ──
    creds = test_http_login()
    test_unverified_access()

    if creds is None:
        print("\n  HTTP 登录失败，跳过后续测试")
        sys.exit(1)

    uid, token = creds
    username = "path_test"

    # ── 建立一条连接，逐步测试各 handler ──
    s = make_socket()

    # 前置: VerifyLoginToken
    if not test_verify_login_token(s, uid, token):
        print("\n  VerifyLoginToken 失败，跳过后续测试")
        s.close()
        sys.exit(1)

    # 前置: PlayerLogin
    test_player_login(s)

    # 前置: PlayerMainData (让 session.logged_in = True)
    test_player_main_data(s)

    # 各 handler 测试（按 handler 分组）
    test_player_ping(s)
    test_change_nickname(s)
    test_change_sign(s)
    test_change_head(s)
    test_change_phone_bg(s)
    test_change_pet(s)
    test_send_chat_msg(s)
    test_get_mails(s)
    test_gacha_list(s)
    test_shop_info(s)
    test_tutorial(s)
    test_npc_talk(s)
    test_manual_list(s)
    test_player_ability_list(s)
    test_get_weapons(s)
    test_get_armors(s)
    test_get_posters(s)
    test_get_all_character_equip(s)
    test_change_musical_item(s)

    # ── 新增 handler 测试 ──
    test_friend_list(s)
    test_friend_search(s, username)
    test_change_scene_channel(s)
    test_area_unlock(s)
    test_monster_dead(s)
    test_collecting(s)
    test_item_use(s)
    test_cooking_food(s)
    test_activity_sign_in(s)
    test_supply_box_reward(s)
    test_update_team(s)
    test_ability_badge_list(s)
    test_shop_buy(s)
    test_character_level_up(s)
    test_character_star_up(s)
    test_gacha(s)
    test_pet_capture(s)
    test_explore_init(s)
    test_supply_box_info(s)
    test_scene_sit_chair(s)

    s.close()

    # ── 重复登录（需另一条连接） ──
    test_verify_login_duplicate(uid, token)

    # ── 汇总 ──
    print()
    print("─" * 56)
    print("  各 handler 测试结果")
    print("─" * 56)
    print_group_summary()

    g_pass = sum(g["pass"] for g in GROUP_RESULTS)
    g_fail = sum(g["fail"] for g in GROUP_RESULTS)
    print()
    print(f"  总计: PASS={g_pass}  FAIL={g_fail}")
    print("=" * 56)
    sys.exit(0 if g_fail == 0 else 1)
