import os
import shutil
import tempfile
import unittest

from hostwatch import processes
from hostwatch.processes import Row

PAGE = 4096
MEM_TOTAL_KB = 1024 * 1024  # 1 GiB


class FakeProc:
    """A minimal /proc tree in a temp dir."""

    def __init__(self):
        self.root = tempfile.mkdtemp()
        with open(os.path.join(self.root, "meminfo"), "w") as fh:
            fh.write(f"MemTotal:       {MEM_TOTAL_KB} kB\nMemFree:  1000 kB\n")
        os.mkdir(os.path.join(self.root, "self"))  # non-numeric entries are ignored

    def add(self, pid, comm, ticks, uid=0, rss_pages=0):
        d = os.path.join(self.root, str(pid))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "comm"), "w") as fh:
            fh.write(comm + "\n")
        with open(os.path.join(d, "status"), "w") as fh:
            fh.write(f"Name:\t{comm}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        with open(os.path.join(d, "statm"), "w") as fh:
            fh.write(f"1000 {rss_pages} 0 0 0 0 0\n")
        self.set_ticks(pid, comm, ticks)

    def set_ticks(self, pid, comm, ticks):
        utime, stime = ticks // 2, ticks - ticks // 2
        with open(os.path.join(self.root, str(pid), "stat"), "w") as fh:
            fh.write(f"{pid} ({comm}) S 1 1 1 0 -1 4194304 100 0 0 0 {utime} {stime} 0 0 20 0 1 0 5 0\n")

    def remove(self, pid):
        shutil.rmtree(os.path.join(self.root, str(pid)))

    def cleanup(self):
        shutil.rmtree(self.root, True)


class TopProcessesTest(unittest.TestCase):
    def setUp(self):
        self.proc = FakeProc()
        self.addCleanup(self.proc.cleanup)
        self.now = 0.0

    def clock(self):
        return self.now

    def sample(self, between, **kw):
        def sleep(seconds):
            self.now += seconds
            between()
        return processes.top_processes(proc_root=self.proc.root, sleep=sleep, clock=self.clock,
                                       clk_tck=100, page_size=PAGE, **kw)

    def test_current_use_not_lifetime_average(self):
        # "old" used lots of CPU long ago (huge lifetime ticks) but is idle now;
        # "busy" was idle for hours and now uses a full core.
        self.proc.add(100, "old", 500000)
        self.proc.add(200, "busy", 10, rss_pages=PAGE * 64 // PAGE)
        rows = self.sample(lambda: self.proc.set_ticks(200, "busy", 10 + 100), own_pid=1)
        self.assertEqual(rows[0].pid, 200)
        self.assertAlmostEqual(rows[0].cpu, 100.0)
        self.assertEqual(rows[1].pid, 100)
        self.assertAlmostEqual(rows[1].cpu, 0.0)

    def test_own_process_excluded(self):
        self.proc.add(300, "python3", 0)
        self.proc.add(301, "other", 0)
        rows = self.sample(lambda: self.proc.set_ticks(300, "python3", 90), own_pid=300)
        self.assertEqual([r.pid for r in rows], [301])

    def test_appearing_and_exiting_processes_skipped(self):
        self.proc.add(400, "leaving", 0)
        self.proc.add(401, "staying", 0)

        def between():
            self.proc.remove(400)
            self.proc.add(402, "arriving", 50)

        rows = self.sample(between, own_pid=1)
        self.assertEqual([r.pid for r in rows], [401])

    def test_comm_with_spaces_and_parens(self):
        self.proc.add(500, "Web (Content) x", 0)
        rows = self.sample(lambda: self.proc.set_ticks(500, "Web (Content) x", 25), own_pid=1)
        self.assertEqual(rows[0].name, "Web (Content) x")
        self.assertAlmostEqual(rows[0].cpu, 25.0)

    def test_memory_percent_and_ordering(self):
        # 2621 pages * 4096 B = ~1 % of 1 GiB; equal CPU -> higher memory first.
        self.proc.add(600, "small", 0, rss_pages=262)
        self.proc.add(601, "big", 0, rss_pages=2621)
        rows = self.sample(lambda: None, own_pid=1)
        self.assertEqual([r.pid for r in rows], [601, 600])
        self.assertAlmostEqual(rows[0].mem, 2621 * PAGE / (MEM_TOTAL_KB * 1024) * 100)

    def test_top_n(self):
        for pid in range(700, 710):
            self.proc.add(pid, f"p{pid}", 0)

        def between():
            for pid in range(700, 710):
                self.proc.set_ticks(pid, f"p{pid}", pid - 700)

        rows = self.sample(between, own_pid=1)
        self.assertEqual([r.pid for r in rows], [709, 708, 707, 706, 705])

    def test_unreadable_proc_gives_empty(self):
        rows = processes.top_processes(proc_root=os.path.join(self.proc.root, "missing"),
                                       sleep=lambda s: None, clk_tck=100, page_size=PAGE)
        self.assertEqual(rows, [])


class FormatTableTest(unittest.TestCase):
    def test_alignment_and_truncation(self):
        table = processes.format_table([
            Row(2412, "alice", 98.04, 3.14, "firefox"),
            Row(911, "averyverylongname", 2.0, 0.4, "a-very-long-process-name"),
        ])
        lines = table.split("\n")
        self.assertEqual(lines[0], "```")
        self.assertEqual(lines[-1], "```")
        self.assertEqual(lines[1], "    PID USER      CPU%  MEM%  NAME")
        self.assertEqual(lines[2], "   2412 alice     98.0   3.1  firefox")
        self.assertEqual(lines[3], "    911 averyve+   2.0   0.4  a-very-long-pr+")
        self.assertLessEqual(max(len(l) for l in lines), 45)

    def test_host_values_shown_literally(self):
        table = processes.format_table([Row(4242, "mallory", 99.0, 0.1, "```<!channel>")])
        self.assertEqual(table.count("```"), 2)
        self.assertTrue(table.startswith("```\n") and table.endswith("\n```"))
        self.assertNotIn("<!", table)
        self.assertIn("ˋˋˋ&lt;!channel&gt;", table)

    def test_escaping_keeps_columns_aligned(self):
        table = processes.format_table([Row(1, "a&b", 1.0, 1.0, "x\ty\x1b"),
                                        Row(2, "alice", 1.0, 1.0, "y")])
        lines = table.split("\n")
        self.assertEqual(lines[2], "      1 a&amp;b        1.0   1.0  x?y?")
        self.assertEqual(lines[3], "      2 alice      1.0   1.0  y")
        # As Slack renders it (one character per entity), the columns line up.
        self.assertEqual(lines[2].replace("&amp;", "&").index("1.0"), lines[3].index("1.0"))

    def test_empty(self):
        self.assertEqual(processes.format_table([]), "```\n(no process data)\n```")


if __name__ == "__main__":
    unittest.main()
