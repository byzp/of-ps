import asyncio
import contextlib
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
from proto.net_pb2 import CreatePayOrderReq, PlayerLoginReq, ScenePlayer, SceneTeam, StatusCode, UploadPhotoShareReq, Vector3
import handlers.CreatePayOrder as payment
import handlers.PlayerLogin as player_login
import handlers.UploadPhotoShare as upload
import http_server.server as http_server
import server.photo_share as photo_share
import server.scene_data as scene_data
import utils.db as db
import utils.pb_create as pb_create
import utils.res_loader as res_loader


class FakeSession:
    def __init__(self, player_id=1000000):
        self.player_id = player_id
        self.player_name = "Synthetic"
        self.scene_id = 1
        self.channel_id = 1
        self.pos = {}
        self.scene_player = ScenePlayer()
        self.logged_in = False
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class DatabaseHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        self.old_auto = Config.ALLOW_AUTO_REGISTER
        Config.DB_PATH = str(self.root / "player.db")
        Config.IN_MEMORY = False
        Config.ALLOW_AUTO_REGISTER = False
        db.exit()

    def tearDown(self):
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory
        Config.ALLOW_AUTO_REGISTER = self.old_auto

    def test_disk_database_persists_and_passwords_are_hashed(self):
        db.init()
        user = db.create_sdk_user("local-user", "correct horse battery staple")
        self.assertIsNone(db.get_sdk_user_info("unknown", "correct horse battery staple"))
        self.assertIsNone(db.get_sdk_user_info("local-user", "wrong password"))
        self.assertEqual(db.get_sdk_user_info("local-user", "correct horse battery staple")["id"], user["id"])
        with sqlite3.connect(Config.DB_PATH) as connection:
            stored = connection.execute("SELECT password FROM users WHERE id=?", (user["id"],)).fetchone()[0]
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertNotIn("correct horse battery staple", stored)
        self.assertTrue(db.verify_sdk_user_info(user["id"], user["user_token"]))
        self.assertFalse(db.verify_sdk_user_info(user["id"], ""))
        self.assertNotIn(0, db.get_player_ids())
        db.exit()
        db.init()
        self.assertEqual(db.get_sdk_user_info("local-user", "correct horse battery staple")["id"], user["id"])

    def test_transaction_rolls_back_failed_write(self):
        db.init()
        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            with db.transaction():
                db.conn.execute("INSERT INTO users(username,password,user_token) VALUES('rollback','x','x')")
                raise RuntimeError("synthetic")
        self.assertIsNone(db.conn.execute("SELECT 1 FROM users WHERE username='rollback'").fetchone())

    def test_memory_snapshot_can_be_read_while_server_is_running(self):
        Config.IN_MEMORY = True
        db.init()
        user = db.create_sdk_user("memory-user", "memory password")
        db.save()
        with sqlite3.connect(Config.DB_PATH) as connection:
            row = connection.execute("SELECT username FROM users WHERE id=?", (user["id"],)).fetchone()
        self.assertEqual(row[0], "memory-user")
        self.assertEqual(list(self.root.glob("player.db.tmp-*")), [])

    def test_legacy_achieve_foreign_key_is_repaired_without_data_loss(self):
        db.init()
        db.conn.execute('DROP TABLE achieve')
        db.conn.execute('''CREATE TABLE achieve (
            player_id INTEGER NOT NULL, achieve_id INTEGER NOT NULL, achieve_blob BLOB NOT NULL,
            PRIMARY KEY(player_id, achieve_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE,
            FOREIGN KEY(achieve_id) REFERENCES players(player_id) ON DELETE CASCADE
        )''')
        db.conn.execute('INSERT INTO players(player_id,player_name) VALUES(?,?)', (1000000, "Existing"))
        db.conn.execute('PRAGMA foreign_keys=OFF')
        db.conn.execute('INSERT INTO achieve VALUES(?,?,?)', (1000000, 999999, b'blob'))
        db.conn.execute('PRAGMA foreign_keys=ON')
        db.exit()
        db.init()
        invalid = [row for row in db.conn.execute('PRAGMA foreign_key_list(achieve)') if row[2] == 'players' and row[3] == 'achieve_id']
        self.assertEqual(invalid, [])
        self.assertEqual(db.conn.execute('SELECT achieve_blob FROM achieve WHERE achieve_id=999999').fetchone()[0], b'blob')

    def test_player_initialization_rolls_back_partial_rows(self):
        db.init()
        with patch.object(db, 'add_character', side_effect=RuntimeError('synthetic init failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic init failure'):
                db.init_player(42)
        self.assertIsNone(db.conn.execute('SELECT 1 FROM players WHERE player_id=42').fetchone())
        self.assertIsNone(db.conn.execute('SELECT 1 FROM garden_info WHERE player_id=42').fetchone())


class UploadHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_cwd = os.getcwd()
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self.old_cwd)
        Config.DB_PATH = str(Path(self.tmp.name) / "player.db")
        Config.IN_MEMORY = False
        db.exit()
        db.init()
        db.conn.execute("INSERT INTO players(player_id,player_name) VALUES(?,?)", (1000000, "Synthetic"))
        photo_share.photos.clear()
        photo_share.extra_upload_grid.clear()

    def tearDown(self):
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory

    def test_oversized_upload_has_no_side_effects(self):
        session = FakeSession()
        request = UploadPhotoShareReq(file=b"x" * 32)
        with patch.object(Config, "PHOTO_MAX_BYTES", 16), \
             patch.object(upload.db, "get_players_info", return_value=[41101, 101001]), \
             patch.object(upload.achieve_track, "collection") as achievement, \
             patch.object(photo_share, "new_photo_code") as code:
            upload.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_BAD_REQ)
        achievement.assert_not_called()
        code.assert_not_called()
        self.assertEqual(photo_share.photos, {})
        self.assertFalse(Path("data/photos").exists())

    def test_quota_is_checked_before_code_file_or_achievement(self):
        session = FakeSession()
        now = int(time.time())
        photo_share.photos = {
            index: {"player_id": session.player_id, "upload_time": now}
            for index in range(photo_share.UPLOAD_MAX_BASE)
        }
        request = UploadPhotoShareReq(file=b"small")
        with patch.object(upload.db, "get_players_info", return_value=[41101, 101001]), \
             patch.object(upload.achieve_track, "collection") as achievement, \
             patch.object(photo_share, "new_photo_code") as code:
            upload.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_PS_UPLOAD_LIMIT)
        achievement.assert_not_called()
        code.assert_not_called()
        self.assertFalse(Path("data/photos").exists())

    def test_snapshot_is_detached_from_mutable_state(self):
        photo_share.photos[1] = {"likes": {2}}
        snapshot = photo_share._snapshot()
        photo_share.photos[1]["likes"].add(3)
        self.assertEqual(snapshot["photos"][1]["likes"], {2})

    def test_daily_limit_survives_photo_deletion(self):
        session = FakeSession()
        today = time.strftime('%Y-%m-%d', time.localtime())
        db.set_kv(session.player_id, 'photo_upload_daily', today, Config.PHOTO_DAILY_UPLOAD_LIMIT)
        request = UploadPhotoShareReq(file=b"small")
        with patch.object(upload.db, "get_players_info", return_value=[41101, 101001]), \
             patch.object(photo_share, "new_photo_code") as code:
            upload.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_PS_UPLOAD_LIMIT)
        code.assert_not_called()
        self.assertFalse(Path("data/photos").exists())

    def test_achievement_failure_does_not_fail_committed_upload(self):
        session = FakeSession()
        request = UploadPhotoShareReq(file=b"small")
        with patch.object(upload.db, "get_players_info", return_value=[41101, 101001]), \
             patch.object(upload.achieve_track, "collection", side_effect=RuntimeError("synthetic achievement failure")):
            upload.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_OK)
        self.assertEqual(len(photo_share.photos), 1)
        self.assertTrue(any(Path("data/photos").glob("*.bin")))

    def test_file_write_failure_rolls_back_quota_and_record(self):
        session = FakeSession()
        request = UploadPhotoShareReq(file=b"small")
        today = time.strftime('%Y-%m-%d', time.localtime())
        with patch.object(upload.db, "get_players_info", return_value=[41101, 101001]), \
             patch("builtins.open", side_effect=OSError("synthetic disk failure")):
            with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                upload.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(photo_share.photos, {})
        self.assertIsNone(db.get_kv(session.player_id, 'photo_upload_daily', today))
        self.assertEqual(list(Path("data/photos").glob("*.tmp")), [])

    def test_load_removes_orphaned_photo_files(self):
        directory = Path("data/photos")
        directory.mkdir(parents=True)
        orphan = directory / "999.bin"
        orphan.write_bytes(b"orphan")
        with patch.object(db, "get_kv", return_value=None), \
             patch.object(photo_share, "_start_autosave"):
            photo_share.load()
        self.assertFalse(orphan.exists())


class PaymentHardeningTests(unittest.TestCase):
    def test_default_rejects_payment_without_grant(self):
        session = FakeSession()
        request = CreatePayOrderReq(shop_id=1, grid_id=1)
        with patch.object(Config, "REJECT_PAYMENT", True), \
             patch("utils.item_mgr.grant_single_item") as grant:
            payment.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_Not_Payment)
        grant.assert_not_called()

    def test_disabling_reject_flag_without_provider_still_denies(self):
        session = FakeSession()
        request = CreatePayOrderReq(shop_id=1, grid_id=1)
        with patch.object(Config, "REJECT_PAYMENT", False), \
             patch.object(Config, "PAYMENT_PROVIDER_ENABLED", False, create=True), \
             patch("utils.item_mgr.grant_single_item") as grant:
            payment.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_Not_Payment)
        self.assertEqual(session.sent[0][1].result_str, "payment unavailable")
        grant.assert_not_called()

    def test_invalid_product_is_rejected_before_order_creation(self):
        session = FakeSession()
        request = CreatePayOrderReq(shop_id=404, grid_id=404)
        with patch.object(Config, "REJECT_PAYMENT", False), \
             patch.object(Config, "PAYMENT_PROVIDER_ENABLED", True, create=True), \
             patch.object(Config, "PAYMENT_CALLBACK_SECRET", "s" * 32, create=True), \
             patch.dict(res_loader.res, {"Shop": {"grid": {"datas": []}, "pool": {"datas": []}}}, clear=True):
            payment.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_BAD_REQ)
        self.assertEqual(session.sent[0][1].order_id, "")


class ResourceHardeningTests(unittest.TestCase):
    def test_init_updates_existing_imported_dictionary_reference(self):
        existing = db.res
        res_loader.init()
        self.assertIs(existing, res_loader.res)
        self.assertIn("Character", existing)

    def test_missing_resource_directory_fails_before_listen(self):
        with tempfile.TemporaryDirectory() as directory:
            images = Path(directory) / "images"
            images.mkdir()
            with patch.object(res_loader, "data_dir", str(Path(directory) / "missing")), \
                 patch.object(res_loader, "img_dir", str(images)):
                with self.assertRaisesRegex(FileNotFoundError, "Required resource directory"):
                    res_loader.init()

    def test_remote_session_close_does_not_require_socket(self):
        from network.remote_link import RemoteSession
        session = object.__new__(RemoteSession)
        session.running = True
        session.close()
        self.assertFalse(session.running)


class LocationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        Config.DB_PATH = str(Path(self.tmp.name) / "player.db")
        Config.IN_MEMORY = False
        db.exit()
        db.init()
        db.conn.execute("INSERT INTO players(player_id,player_name) VALUES(?,?)", (1000000, "Existing"))
        scene_data._last_location_save.clear()

    def tearDown(self):
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory
        scene_data._last_location_save.clear()

    def session(self, player_id=1000000):
        session = FakeSession(player_id)
        session.scene_id = 1002
        session.channel_id = 77
        session.pos = {1002: Vector3(x=123, y=456, z=789)}
        return session

    def test_scene_channel_and_position_survive_restart(self):
        first = self.session()
        first.scene_player.team.char1.rot.CopyFrom(Vector3(x=10, y=20, z=30))
        scene_data.save_session_location(first, force=True)
        db.exit()
        db.init()
        second = self.session()
        second.scene_id = 1
        second.channel_id = 1
        second.pos = {}
        self.assertTrue(scene_data.restore_session_location(second))
        self.assertEqual((second.scene_id, second.channel_id), (1002, 77))
        self.assertEqual(second.pos[1002], Vector3(x=123, y=456, z=789))
        self.assertEqual(second.scene_player.team.char1.rot, Vector3(x=10, y=20, z=30))

    def test_movement_saves_are_throttled(self):
        session = self.session()
        with patch.object(db, "set_kv") as write:
            scene_data.save_session_location(session, force=True)
            scene_data.save_session_location(session)
            self.assertEqual(write.call_count, 1)

    def test_reconnect_request_uses_saved_location(self):
        session = self.session()
        session.scene_id = 1
        session.channel_id = 1
        session.pos = {}

        def restore(current):
            current.scene_id = 1002
            current.channel_id = 77
            return True

        request = PlayerLoginReq(is_reconnect=True)
        with patch.object(player_login.db, "get_players_info", side_effect=[[10], ("cn", 1, 28800, "Existing", "token")]), \
             patch.object(player_login.db, "get_analysis_account_id", return_value="synthetic"), \
             patch.object(player_login.achieve_track, "batch", return_value=contextlib.nullcontext()), \
             patch.object(player_login.achieve_track, "daily_login"), \
             patch.object(player_login.achieve_track, "captain_level"), \
             patch.object(player_login.scene_data, "restore_session_location", side_effect=restore):
            player_login.Handler().handle(session, request.SerializeToString(), 1)
        response = session.sent[0][1]
        self.assertEqual(response.status, StatusCode.StatusCode_OK)
        self.assertTrue(response.is_reconnect)
        self.assertTrue(response.reconnect_success)
        self.assertEqual((response.scene_id, response.channel_id), (1002, 77))

    def test_duplicate_reconnect_on_logged_in_session_is_rejected(self):
        session = self.session()
        session.logged_in = True
        with patch.object(player_login.db, "get_players_info") as lookup:
            player_login.Handler().handle(session, PlayerLoginReq(is_reconnect=True).SerializeToString(), 1)
        lookup.assert_not_called()
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_FAIL)

    def test_scene_player_rebuild_preserves_saved_rotation(self):
        session = self.session()
        session.scene_player.team.char1.rot.CopyFrom(Vector3(x=1, y=2, z=3))
        with patch.object(pb_create.db, "get_players_info", return_value=["", ()]), \
             patch.object(pb_create, "make_SceneTeam", return_value=SceneTeam()):
            pb_create.make_ScenePlayer(session)
        self.assertEqual(session.scene_player.team.char1.pos, Vector3(x=123, y=456, z=789))
        self.assertEqual(session.scene_player.team.char1.rot, Vector3(x=1, y=2, z=3))


class HttpHardeningTests(unittest.TestCase):
    def test_registration_does_not_return_token(self):
        with tempfile.TemporaryDirectory() as directory:
            old_path = Config.DB_PATH
            old_memory = Config.IN_MEMORY
            Config.DB_PATH = str(Path(directory) / "player.db")
            Config.IN_MEMORY = False
            db.exit()
            try:
                db.init()
                response = asyncio.run(http_server.api_register(
                    http_server.RegistrationRequest(username="http-user", password="http password")
                ))
                payload = json.loads(response.body)
                self.assertTrue(payload["success"])
                self.assertNotIn("user_token", payload)
                login_response = asyncio.run(http_server.api_login(
                    http_server.LoginRequest(username="http-user", password="http password"),
                ))
                login_payload = json.loads(login_response.body)
                self.assertTrue(login_payload["successUrl"].startswith("http://127.0.0.1:21000/loginSuccess.html?"))
                self.assertNotIn("sdkapi-of.inutan.com", login_payload["successUrl"])
            finally:
                db.exit()
                Config.DB_PATH = old_path
                Config.IN_MEMORY = old_memory


if __name__ == "__main__":
    unittest.main(verbosity=2)
