import os
import shutil
import tempfile
import unittest
from unittest import mock

from hostwatch import state


class StateTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        patcher = mock.patch.dict(os.environ, {state.STATE_DIR_ENV: self.dir})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.marker = os.path.join(self.dir, state.MARKER)

    def test_mark_then_consume(self):
        self.assertTrue(state.mark_clean())
        self.assertTrue(os.path.exists(self.marker))
        self.assertTrue(state.consume_clean())
        self.assertFalse(os.path.exists(self.marker))

    def test_second_consume_reports_unclean(self):
        state.mark_clean()
        state.consume_clean()
        self.assertFalse(state.consume_clean())

    def test_nothing_recorded_is_unclean(self):
        self.assertFalse(state.consume_clean())

    def test_peek_does_not_remove(self):
        state.mark_clean()
        self.assertTrue(state.peek_clean())
        self.assertTrue(state.peek_clean())
        self.assertTrue(os.path.exists(self.marker))

    def test_default_dir(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(state._marker_path(),
                             os.path.join("/var/lib/hostwatch", "clean_shutdown"))

    @mock.patch.object(state.log, "error")
    def test_missing_dir_is_handled(self, error):
        shutil.rmtree(self.dir)
        self.assertFalse(state.mark_clean())
        error.assert_called_once()
        self.assertFalse(state.consume_clean())
        self.assertFalse(state.peek_clean())


class LoginRecentlyNotifiedTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        patcher = mock.patch.dict(os.environ, {state.STATE_DIR_ENV: self.dir})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_first_call_is_not_recent(self):
        self.assertFalse(state.login_recently_notified("alice:SSH:1.2.3.4", 60))

    def test_second_call_within_window_is_recent(self):
        state.login_recently_notified("alice:SSH:1.2.3.4", 60)
        self.assertTrue(state.login_recently_notified("alice:SSH:1.2.3.4", 60))

    def test_different_key_is_independent(self):
        state.login_recently_notified("alice:SSH:1.2.3.4", 60)
        self.assertFalse(state.login_recently_notified("bob:SSH:1.2.3.4", 60))

    def test_call_past_the_window_is_not_recent(self):
        with mock.patch.object(state.time, "time", return_value=1000.0):
            state.login_recently_notified("alice:SSH:1.2.3.4", 60)
        with mock.patch.object(state.time, "time", return_value=1061.0):
            self.assertFalse(state.login_recently_notified("alice:SSH:1.2.3.4", 60))

    def test_zero_window_disables_it(self):
        state.login_recently_notified("alice:SSH:1.2.3.4", 0)
        self.assertFalse(state.login_recently_notified("alice:SSH:1.2.3.4", 0))

    @mock.patch.object(state.log, "error")
    def test_unwritable_dir_is_handled(self, error):
        marker_parent = os.path.join(self.dir, state.LOGIN_COOLDOWN_DIR)
        open(marker_parent, "w").close()  # a file where a directory is needed
        self.assertFalse(state.login_recently_notified("alice:SSH:1.2.3.4", 60))
        error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
