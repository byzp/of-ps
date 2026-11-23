"""隔离数据库验证 Steam 禁注册热补丁后的网页命名及教程入口。"""

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from config import Config
from proto import net_pb2 as pb
from utils import db, res_loader
from handlers.PlayerLogin import Handler as PlayerLogin
from handlers.ChangeSceneChannel import Handler as ChangeScene
from http_server.server import app


class LoginPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="of-login-patch-")
        Config.DB_PATH = str(Path(cls.directory.name) / "player.db")
        Config.IN_MEMORY = False
        Config.SKIP_QUESTS = False
        res_loader.init()
        db.init()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        db.exit()
        cls.directory.cleanup()

    def login(self, username, password="local"):
        return self.client.post(
            "/api/login",
            json={"username": username, "password": password},
        ).json()

    def test_new_character_named_before_game_login_and_tutorial_retained(self):
        response = self.login("test+&中文#")
        self.assertTrue(response["success"])
        params = parse_qs(urlsplit(response["successUrl"]).query)
        self.assertEqual(params["username"], ["test+&中文#"])
        pid = db.get_player_id(int(params["uid"][0]))
        messages = []
        session = SimpleNamespace(
            player_id=pid,
            scene_id=1,
            channel_id=1,
            quests={},
            pos={},
            dungeon=[0, 0, 0, -1],
            temp_pack=[],
            scene_player=pb.ScenePlayer(player_id=pid),
            drop_lock=threading.RLock(),
            drop_items={},
            send=lambda mid, msg, seq: messages.append(
                type(msg).FromString(msg.SerializeToString())
            ),
        )
        PlayerLogin().handle(session, pb.PlayerLoginReq().SerializeToString(), 1)
        rsp = next(m for m in messages if isinstance(m, pb.PlayerLoginRsp))
        self.assertEqual(rsp.player_name, "test+&中文#")
        self.assertEqual(rsp.scene_id, 100)
        # 同账号后续登录不覆盖昵称；离开教学前重连继续进入教学。
        db.set_players_info(pid, "player_name", "RenamedPlayer")
        self.assertTrue(self.login("test+&中文#")["success"])
        self.assertEqual(db.get_players_info(pid, "player_name")[0], "RenamedPlayer")
        ChangeScene().handle(
            session, pb.ChangeSceneChannelReq(scene_id=1).SerializeToString(), 2
        )
        self.assertFalse(db.get_kv(pid, "profile", "tutorial_pending", 0))
        PlayerLogin().handle(session, pb.PlayerLoginReq().SerializeToString(), 3)
        self.assertNotEqual(session.scene_id, 100)
        self.assertFalse(self.login("test+&中文#", password="wrong")["success"])

    def test_account_name_duplicates_and_page(self):
        response = self.login("automatic")
        pid = int(parse_qs(urlsplit(response["successUrl"]).query)["uid"][0])
        self.assertEqual(db.get_players_info(pid, "player_name")[0], "automatic")
        db.set_players_info(pid, "player_name", "taken")
        duplicate = self.login("taken")
        self.assertFalse(duplicate["success"])
        db.set_players_info(pid, "player_name", "automatic")
        self.assertTrue(self.login("taken")["success"])
        self.assertFalse(self.login("x" * 49)["success"])
        for path in ("/open/oauth", "/openapi/oauth"):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertNotIn('id="nickname"', page.text)
            self.assertIn('<html lang="en">', page.text)
            self.assertFalse(any("\u4e00" <= char <= "\u9fff" for char in page.text))
            self.assertIn("successUrl", page.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
