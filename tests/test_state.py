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


if __name__ == "__main__":
    unittest.main()
