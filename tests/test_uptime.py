import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from hostwatch import uptime


def _dt(*args, **kwargs):
    return datetime(*args, tzinfo=timezone.utc, **kwargs)


class TodayUptimeTest(unittest.TestCase):
    def test_several_sessions_in_a_day(self):
        # Boot 08:00, reboot 10:00, boot again, heartbeat at 11:00 (1 h into
        # the second session): 2 h (first session) + 1 h (second) = 3 h.
        entries = [
            {"start": _dt(2026, 10, 11, 8, 0), "end": _dt(2026, 10, 11, 10, 0),
             "reason": "reboot", "estimated": False},
        ]
        result = uptime.today_uptime(entries, _dt(2026, 10, 11, 10, 0, 5),
                                     _dt(2026, 10, 11, 11, 0), tz=timezone.utc)
        self.assertAlmostEqual(result.seconds, 3 * 3600, delta=5)
        self.assertEqual(result.sessions, 2)
        self.assertFalse(result.estimated)

    def test_session_crossing_midnight_counts_only_after_midnight(self):
        entries = [
            {"start": _dt(2026, 10, 10, 22, 0), "end": _dt(2026, 10, 11, 1, 0),
             "reason": "clean", "estimated": False},
        ]
        result = uptime.today_uptime(entries, None, _dt(2026, 10, 11, 2, 0), tz=timezone.utc)
        self.assertEqual(result.seconds, 3600)  # only 00:00-01:00 counts
        self.assertEqual(result.sessions, 1)

    def test_estimated_session_after_power_loss(self):
        entries = [
            {"start": _dt(2026, 10, 11, 8, 0), "end": _dt(2026, 10, 11, 9, 30),
             "reason": "unclean", "estimated": True},
        ]
        result = uptime.today_uptime(entries, None, _dt(2026, 10, 11, 10, 0), tz=timezone.utc)
        self.assertTrue(result.estimated)
        self.assertEqual(result.sessions, 1)

    def test_empty_ledger_counts_only_current_session(self):
        result = uptime.today_uptime([], _dt(2026, 10, 11, 9, 0), _dt(2026, 10, 11, 10, 0),
                                     tz=timezone.utc)
        self.assertEqual(result.seconds, 3600)
        self.assertEqual(result.sessions, 1)
        self.assertFalse(result.estimated)

    def test_empty_ledger_no_current_session(self):
        result = uptime.today_uptime([], None, _dt(2026, 10, 11, 10, 0), tz=timezone.utc)
        self.assertEqual(result.seconds, 0)
        self.assertEqual(result.sessions, 0)

    def test_clock_moved_backwards_excludes_session(self):
        # Recorded start is after its recorded end: never produce a negative total.
        entries = [
            {"start": _dt(2026, 10, 11, 12, 0), "end": _dt(2026, 10, 11, 9, 0),
             "reason": "clean", "estimated": False},
        ]
        result = uptime.today_uptime(entries, None, _dt(2026, 10, 11, 13, 0), tz=timezone.utc)
        self.assertEqual(result.seconds, 0)
        self.assertEqual(result.sessions, 0)

    def test_current_session_clock_behind_boot_time_excluded(self):
        result = uptime.today_uptime([], _dt(2026, 10, 11, 10, 0), _dt(2026, 10, 11, 9, 0),
                                     tz=timezone.utc)
        self.assertEqual(result.sessions, 0)

    def test_open_entry_in_ledger_is_ignored(self):
        entries = [{"start": _dt(2026, 10, 11, 8, 0), "end": None,
                    "reason": None, "estimated": False}]
        result = uptime.today_uptime(entries, None, _dt(2026, 10, 11, 10, 0), tz=timezone.utc)
        self.assertEqual(result.sessions, 0)


class FormatUptimeTodayTest(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(uptime.format_uptime_today(5 * 3600 + 42 * 60, 2, False),
                         "5 h 42 min (2 sessions)")

    def test_estimated(self):
        self.assertEqual(uptime.format_uptime_today(5 * 3600 + 40 * 60, 2, True),
                         "~5 h 40 min (2 sessions)")

    def test_singular_session(self):
        self.assertEqual(uptime.format_uptime_today(3600, 1, False), "1 h 0 min (1 session)")


class LoadLedgerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "uptime.json")

    def test_missing_file_is_absent(self):
        entries, status = uptime.load_ledger(self.path)
        self.assertEqual((entries, status), ([], "absent"))

    def test_corrupt_json_is_corrupt(self):
        with open(self.path, "w") as fh:
            fh.write("{not json")
        entries, status = uptime.load_ledger(self.path)
        self.assertEqual((entries, status), ([], "corrupt"))

    def test_non_list_json_is_corrupt(self):
        with open(self.path, "w") as fh:
            json.dump({"oops": True}, fh)
        entries, status = uptime.load_ledger(self.path)
        self.assertEqual((entries, status), ([], "corrupt"))

    def test_valid_file(self):
        with open(self.path, "w") as fh:
            json.dump([{"start": "2026-10-11T08:00:00+00:00", "end": None,
                       "reason": None, "estimated": False}], fh)
        entries, status = uptime.load_ledger(self.path)
        self.assertEqual(status, "ok")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["start"], _dt(2026, 10, 11, 8, 0))

    def test_bad_individual_record_is_dropped_not_fatal(self):
        with open(self.path, "w") as fh:
            json.dump([
                {"start": "not a timestamp"},
                {"start": "2026-10-11T08:00:00+00:00", "end": None,
                 "reason": None, "estimated": False},
            ], fh)
        entries, status = uptime.load_ledger(self.path)
        self.assertEqual(status, "ok")
        self.assertEqual(len(entries), 1)


class PruneTest(unittest.TestCase):
    def test_old_entries_dropped_open_kept(self):
        now = _dt(2026, 10, 11, 0, 0)
        entries = [
            {"start": now - timedelta(days=100), "end": now - timedelta(days=100),
             "reason": "clean", "estimated": False},
            {"start": now - timedelta(days=10), "end": now - timedelta(days=10),
             "reason": "clean", "estimated": False},
            {"start": now, "end": None, "reason": None, "estimated": False},
        ]
        pruned = uptime.prune(entries, 90, now)
        self.assertEqual(len(pruned), 2)
        self.assertTrue(any(e["end"] is None for e in pruned))

    def test_old_orphaned_open_entry_is_pruned(self):
        # An entry left open by a session that was never closed (e.g. a
        # ledger write failure at shutdown) is not the last entry, so it is
        # not "the current session" and ages out like any other.
        now = _dt(2026, 10, 11, 0, 0)
        entries = [
            {"start": now - timedelta(days=100), "end": None,
             "reason": None, "estimated": False},
            {"start": now, "end": None, "reason": None, "estimated": False},
        ]
        pruned = uptime.prune(entries, 90, now)
        self.assertEqual(len(pruned), 1)
        self.assertEqual(pruned[0]["start"], now)

    def test_recent_orphaned_open_entry_is_kept(self):
        now = _dt(2026, 10, 11, 0, 0)
        entries = [
            {"start": now - timedelta(days=5), "end": None,
             "reason": None, "estimated": False},
            {"start": now, "end": None, "reason": None, "estimated": False},
        ]
        pruned = uptime.prune(entries, 90, now)
        self.assertEqual(len(pruned), 2)


class LedgerWriteTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        patcher = mock.patch.dict(os.environ, {uptime.STATE_DIR_ENV: self.dir})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_record_boot_appends_open_entry(self):
        now = _dt(2026, 10, 11, 8, 0)
        self.assertTrue(uptime.record_boot(now, 90))
        entries, status = uptime.load_ledger()
        self.assertEqual(status, "ok")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["start"], now)
        self.assertIsNone(entries[0]["end"])

    def test_two_sequential_writers_both_land(self):
        uptime.record_boot(_dt(2026, 10, 11, 8, 0), 90)
        uptime.close_open_entry(_dt(2026, 10, 11, 10, 0), "clean", 90)
        uptime.record_boot(_dt(2026, 10, 11, 10, 5), 90)
        entries, status = uptime.load_ledger()
        self.assertEqual(status, "ok")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["end"], _dt(2026, 10, 11, 10, 0))
        self.assertIsNone(entries[1]["end"])

    def test_close_open_entry_no_open_entry_is_noop(self):
        uptime.record_boot(_dt(2026, 10, 11, 8, 0), 90)
        uptime.close_open_entry(_dt(2026, 10, 11, 9, 0), "clean", 90)
        before, _ = uptime.load_ledger()
        uptime.close_open_entry(_dt(2026, 10, 11, 9, 30), "clean", 90)
        after, _ = uptime.load_ledger()
        self.assertEqual(before, after)

    def test_close_open_entry_without_end_time_uses_start(self):
        # No last-alive timestamp was ever recorded: zero-length estimate.
        uptime.record_boot(_dt(2026, 10, 11, 8, 0), 90)
        uptime.close_open_entry(None, "unclean", 90)
        entries, _ = uptime.load_ledger()
        self.assertEqual(entries[0]["end"], entries[0]["start"])
        self.assertTrue(entries[0]["estimated"])

    def test_close_open_entry_stale_end_before_start_falls_back_to_start(self):
        # A last-alive reading left over from an earlier session (this one
        # crashed before ever updating it) must not produce end < start.
        start = _dt(2026, 10, 11, 8, 0)
        stale_last_alive = _dt(2026, 10, 11, 7, 0)
        uptime.record_boot(start, 90)
        uptime.close_open_entry(stale_last_alive, "unclean", 90, estimated=True)
        entries, _ = uptime.load_ledger()
        self.assertEqual(entries[0]["end"], start)
        self.assertTrue(entries[0]["estimated"])

    def test_close_open_entry_now_param_controls_retention_cutoff(self):
        # retention_days=10: pick an old entry whose end (2026-10-11) falls
        # between the cutoff a stale end_time would imply (2026-10-10, were
        # "now" to default to it) and the cutoff the real "now" gives
        # (2026-10-12), so only passing the real "now" prunes it.
        crash_boot = _dt(2026, 10, 20, 8, 0)
        stale_last_alive = _dt(2026, 10, 20, 9, 0)
        real_now = _dt(2026, 10, 22, 0, 0)
        uptime._atomic_write(uptime._ledger_path(), json.dumps([
            {"start": "2026-10-10T23:00:00+00:00", "end": "2026-10-11T00:00:00+00:00",
             "reason": "clean", "estimated": False},
        ]))
        uptime.record_boot(crash_boot, 10)
        uptime.close_open_entry(stale_last_alive, "unclean", 10, estimated=True, now=real_now)
        entries, _ = uptime.load_ledger()
        self.assertEqual(len(entries), 1)  # the 2026-10-10/11 entry was pruned
        self.assertEqual(entries[0]["start"], crash_boot)

    def test_pruning_runs_on_every_write(self):
        old = _dt(2026, 1, 1, 0, 0)
        uptime._atomic_write(uptime._ledger_path(), json.dumps([
            {"start": "2026-01-01T00:00:00+00:00", "end": "2026-01-01T01:00:00+00:00",
             "reason": "clean", "estimated": False},
        ]))
        uptime.record_boot(_dt(2026, 10, 11, 8, 0), 90)
        entries, _ = uptime.load_ledger()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["start"], _dt(2026, 10, 11, 8, 0))

    @mock.patch.object(uptime.log, "error")
    def test_lock_timeout_is_reported_not_raised(self, error):
        with mock.patch.object(uptime, "_locked", side_effect=TimeoutError("locked")):
            self.assertFalse(uptime.record_boot(_dt(2026, 10, 11, 8, 0), 90))
        error.assert_called_once()

    @mock.patch.object(uptime.log, "error")
    def test_unwritable_dir_is_handled(self, error):
        shutil.rmtree(self.dir)
        open(self.dir, "w").close()  # a file where the state dir should be
        self.addCleanup(os.remove, self.dir)
        self.assertFalse(uptime.record_boot(_dt(2026, 10, 11, 8, 0), 90))
        error.assert_called_once()


class LastAliveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        patcher = mock.patch.dict(os.environ, {uptime.STATE_DIR_ENV: self.dir})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_file_reads_none(self):
        self.assertIsNone(uptime.read_last_alive())

    def test_touch_then_read(self):
        now = _dt(2026, 10, 11, 9, 30)
        self.assertTrue(uptime.touch_last_alive(now))
        read_back = uptime.read_last_alive()
        self.assertAlmostEqual(read_back.timestamp(), now.timestamp(), delta=1)

    def test_corrupt_file_reads_none(self):
        path = os.path.join(self.dir, uptime.LAST_ALIVE_NAME)
        with open(path, "w") as fh:
            fh.write("not a number")
        self.assertIsNone(uptime.read_last_alive())

    @mock.patch.object(uptime.log, "error")
    def test_unwritable_dir_is_handled(self, error):
        shutil.rmtree(self.dir)
        open(self.dir, "w").close()
        self.addCleanup(os.remove, self.dir)
        self.assertFalse(uptime.touch_last_alive(_dt(2026, 10, 11, 9, 30)))
        error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
