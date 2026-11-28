import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server import notice_sync, scene_data
from server.scene_data import _session_list, lock_session


class SessionFinalizationTests(unittest.TestCase):
    def test_finalize_removes_session_and_syncs_after_releasing_lock(self):
        session = SimpleNamespace(
            running=False,
            logged_in=True,
            remote=False,
            player_id=1000000,
            player_name="player",
            scene_id=1,
            channel_id=1,
            send=Mock(),
        )
        with lock_session:
            _session_list.append(session)

        def sync_after_unlock():
            self.assertFalse(lock_session.locked())

        try:
            with patch.object(notice_sync, "_save_local_session"), patch.object(
                notice_sync.mail_rewards, "recover_drops"
            ), patch.object(notice_sync, "up_scene_action"), patch.object(
                notice_sync, "sync_subscriptions", side_effect=sync_after_unlock
            ) as sync:
                finalized = notice_sync.finalize_session(session)
            self.assertTrue(finalized)
            sync.assert_called_once()
            self.assertFalse(session.logged_in)
            self.assertNotIn(session, _session_list)
        finally:
            with lock_session:
                if session in _session_list:
                    _session_list.remove(session)


if __name__ == "__main__":
    unittest.main()
