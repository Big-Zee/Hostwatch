import os
import re
import tempfile
import unittest
from datetime import datetime, timezone

from hostwatch import timefmt


class TimefmtTest(unittest.TestCase):
    def test_warsaw_summer(self):
        moment = datetime(2026, 10, 11, 10, 1, 33, tzinfo=timezone.utc)
        self.assertEqual(timefmt.format_time(moment, "Europe/Warsaw"), "2026-10-11 12:01:33 CEST")

    def test_without_seconds(self):
        moment = datetime(2026, 10, 11, 7, 14, 59, tzinfo=timezone.utc)
        self.assertEqual(timefmt.format_time(moment, "Europe/Warsaw", seconds=False),
                         "2026-10-11 09:14 CEST")
        self.assertEqual(timefmt.format_time(moment, "Europe/Warsaw"), "2026-10-11 09:14:59 CEST")

    def test_warsaw_winter(self):
        moment = datetime(2026, 12, 1, 8, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(timefmt.format_time(moment, "Europe/Warsaw"), "2026-12-01 09:00:00 CET")

    def test_local_format(self):
        text = timefmt.format_time(timefmt.now(), "local")
        self.assertRegex(text, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S")

    def test_kernel_boot_time(self):
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "w") as fh:
            fh.write("cpu  1 2 3\nbtime 1791712893\nprocesses 42\n")
        self.addCleanup(os.remove, path)
        self.assertEqual(timefmt.kernel_boot_time(path),
                         datetime.fromtimestamp(1791712893, timezone.utc))

    def test_kernel_boot_time_missing(self):
        self.assertIsNone(timefmt.kernel_boot_time(os.path.join(tempfile.gettempdir(), "nope")))


class UptimeTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(timefmt.format_uptime(5 * 3600 + 12 * 60 + 59), "up 5 h 12 min")
        self.assertEqual(timefmt.format_uptime(2 * 86400 + 3 * 3600 + 4 * 60), "up 2 d 3 h 4 min")
        self.assertEqual(timefmt.format_uptime(86400 + 30), "up 1 d 0 h 0 min")
        self.assertEqual(timefmt.format_uptime(12 * 60 + 5.5), "up 12 min")
        self.assertEqual(timefmt.format_uptime(42), "up 0 min")

    def test_read_proc_uptime(self):
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "w") as fh:
            fh.write("18720.55 70123.10\n")
        self.addCleanup(os.remove, path)
        self.assertEqual(timefmt.uptime_seconds(path), 18720.55)

    def test_missing_proc_uptime(self):
        self.assertIsNone(timefmt.uptime_seconds(os.path.join(tempfile.gettempdir(), "nope")))


if __name__ == "__main__":
    unittest.main()
