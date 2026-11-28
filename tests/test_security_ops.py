import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
from proto.net_pb2 import OperatePhotoShareReq, PhotoOperateType, SPOperateReq, SPOperateType, StatusCode
import handlers.OperatePhotoShare as photo
import handlers.SPOperate as sp
import server.photo_share as photo_share
import utils.db as db


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class SPOperateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        Config.DB_PATH = str(Path(self.tmp.name) / "player.db")
        Config.IN_MEMORY = False
        db.exit()
        db.init()
        db.conn.execute("INSERT INTO players(player_id,player_name) VALUES(1,'p1')")
        photo_share.sp_state.clear()

    def tearDown(self):
        photo_share.sp_state.clear()
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory

    def test_password_is_hashed_and_verified(self):
        session = FakeSession()
        with patch.object(sp.payment_security, 'password_length', return_value=6):
            sp.Handler().handle(session, SPOperateReq(operate_type=SPOperateType.SPOperateType_Open, password='123456').SerializeToString(), 1)
            stored = photo_share.sp_state[1]['password']
            self.assertTrue(stored.startswith('pbkdf2_sha256$'))
            self.assertNotEqual(stored, '123456')
            sp.Handler().handle(session, SPOperateReq(operate_type=SPOperateType.SPOperateType_Check, password='123456').SerializeToString(), 2)
            self.assertTrue(session.sent[-1][1].sp_check_status)
            sp.Handler().handle(session, SPOperateReq(operate_type=SPOperateType.SPOperateType_Check, password='654321').SerializeToString(), 3)
            self.assertFalse(session.sent[-1][1].sp_check_status)

    def test_change_requires_old_password_and_valid_length(self):
        session = FakeSession()
        photo_share.sp_state[1] = {'password': sp._hash_password('123456'), 'open': True}
        with patch.object(sp.payment_security, 'password_length', return_value=6):
            sp.Handler().handle(session, SPOperateReq(operate_type=SPOperateType.SPOperateType_Change, old_password='000000', password='abcdef').SerializeToString(), 1)
            self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_FAIL)
            sp.Handler().handle(session, SPOperateReq(operate_type=SPOperateType.SPOperateType_Change, old_password='123456', password='abc').SerializeToString(), 1)
            self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_FAIL)

    def test_unknown_operation_is_rejected(self):
        session = FakeSession()
        sp.Handler().handle(session, SPOperateReq(operate_type=SPOperateType.SPOperateType_None).SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_BAD_REQ)


class PhotoOperateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self.old_cwd)
        photo_share.photos.clear()
        directory = Path('data/photos')
        directory.mkdir(parents=True)
        (directory / '100.bin').write_bytes(b'photo')
        photo_share.photos[100] = {
            'player_id': 1, 'likes': set(), 'favorites': set(),
            'is_activity': False, 'activity_id': 0,
        }

    def test_non_owner_cannot_move_or_delete(self):
        session = FakeSession(2)
        photo.Handler().handle(session, OperatePhotoShareReq(code=100, operate_type=PhotoOperateType.PhotoOperateType_MOVE).SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_FAIL)
        photo.Handler().handle(session, OperatePhotoShareReq(code=100, operate_type=PhotoOperateType.PhotoOperateType_DEL).SerializeToString(), 2)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_FAIL)
        self.assertIn(100, photo_share.photos)
        self.assertTrue(Path('data/photos/100.bin').exists())

    def test_owner_delete_removes_record_and_file(self):
        session = FakeSession(1)
        photo.Handler().handle(session, OperatePhotoShareReq(code=100, operate_type=PhotoOperateType.PhotoOperateType_DEL).SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_OK)
        self.assertNotIn(100, photo_share.photos)
        self.assertFalse(Path('data/photos/100.bin').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
