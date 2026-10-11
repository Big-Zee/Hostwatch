import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from hostwatch import sessions
from hostwatch.sessions import Session

LIST_SESSIONS = """\
  2 1000 alice seat0 tty2
  5 1000 alice -     -
  c1  120 gdm   seat0 tty1
  7    0 root  -     -
  8 1000 alice -     -
  9 1001 bob   -     tty3
"""

SHOW_SESSION = """\
Id=2
Name=alice
Type=wayland
Class=user
State=active
Remote=no
RemoteHost=
Service=gdm-password
TTY=tty2

Id=5
Name=alice
Type=tty
Class=user
State=active
Remote=yes
RemoteHost=203.0.113.7
Service=sshd
TTY=pts/0

Id=c1
Name=gdm
Type=wayland
Class=greeter
State=online
Remote=no
RemoteHost=
Service=gdm-launch-environment
TTY=tty1

Id=7
Name=root
Type=unspecified
Class=background
State=active
Remote=no
RemoteHost=
Service=su
TTY=

Id=8
Name=alice
Type=tty
Class=user
State=closing
Remote=yes
RemoteHost=198.51.100.2
Service=sshd
TTY=pts/1

Id=9
Name=bob
Type=tty
Class=user
State=active
Remote=no
RemoteHost=
Service=login
TTY=tty3
"""

WHO = """\
alice    seat0        2026-10-11 11:00 (login screen)
alice    :0           2026-10-11 11:00 (:0)
alice    pts/1        2026-10-11 11:05
bob      pts/0        2026-10-11 12:00 (203.0.113.9)
bob      pts/2        2026-10-11 12:01 (203.0.113.9)
carol    tty3         2026-10-11 12:10
gdm      seat0        2026-10-11 10:59 (login screen)
dave     pts/3        2026-10-11 12:20 (tmux(4242).%0)
"""


def fake_run(outputs):
    """outputs maps the command's first two words to stdout, or to an exception."""
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        key = " ".join(args[:2]) if args[0] == "loginctl" else args[0]
        result = outputs.get(key)
        if isinstance(result, BaseException):
            raise result
        if result is None:
            return SimpleNamespace(stdout="", returncode=1)
        return SimpleNamespace(stdout=result, returncode=0)

    run.calls = calls
    return run


class LogindTest(unittest.TestCase):
    def test_classification_and_filtering(self):
        run = fake_run({"loginctl list-sessions": LIST_SESSIONS, "loginctl show-session": SHOW_SESSION})
        self.assertEqual(sessions.logged_in_users(run=run), [
            Session("alice", "desktop", None, 1),
            Session("alice", "ssh", "203.0.113.7", 1),
            Session("bob", "tty", None, 1),
        ])
        show_args = run.calls[1][0]
        self.assertEqual(show_args[:8], ["loginctl", "show-session", "2", "5", "c1", "7", "8", "9"])
        self.assertIn("RemoteHost", show_args)
        self.assertTrue(all(kw["timeout"] == 2 for _, kw in run.calls))
        self.assertTrue(all(kw["errors"] == "replace" for _, kw in run.calls))

    def test_no_sessions(self):
        run = fake_run({"loginctl list-sessions": ""})
        self.assertEqual(sessions.logged_in_users(run=run), [])
        self.assertEqual(len(run.calls), 1)  # no show-session call, no who fallback

    def test_greeter_only_means_nobody(self):
        greeter = SHOW_SESSION.split("\n\n")[2] + "\n"
        run = fake_run({"loginctl list-sessions": "c1 120 gdm seat0 tty1\n",
                        "loginctl show-session": greeter})
        self.assertEqual(sessions.logged_in_users(run=run), [])

    def test_excluded_account_names(self):
        for name in ("gdm", "gdm-greeter", "gdm-greeter-2", "lightdm", "sddm"):
            record = {"Name": name, "Class": "user", "State": "active", "Type": "x11"}
            self.assertIsNone(sessions.classify_logind(record), name)


class WhoFallbackTest(unittest.TestCase):
    def expected(self):
        return [
            Session("alice", "desktop", None, 2),
            Session("bob", "ssh", "203.0.113.9", 2),
            Session("carol", "tty", None, 1),
        ]

    def test_loginctl_missing(self):
        run = fake_run({"loginctl list-sessions": FileNotFoundError("loginctl"), "who": WHO})
        self.assertEqual(sessions.logged_in_users(run=run), self.expected())

    def test_who_output_decoded_with_replacement(self):
        run = fake_run({"loginctl list-sessions": None, "who": WHO})
        sessions.logged_in_users(run=run)
        self.assertEqual(run.calls[-1][0], ["who"])
        self.assertEqual(run.calls[-1][1]["errors"], "replace")

    def test_loginctl_error_or_timeout(self):
        run = fake_run({"loginctl list-sessions": None, "who": WHO})
        self.assertEqual(sessions.logged_in_users(run=run), self.expected())
        run = fake_run({"loginctl list-sessions": subprocess.TimeoutExpired("loginctl", 2), "who": WHO})
        self.assertEqual(sessions.logged_in_users(run=run), self.expected())

    def test_show_session_failure_falls_back(self):
        run = fake_run({"loginctl list-sessions": LIST_SESSIONS, "loginctl show-session": None,
                        "who": WHO})
        self.assertEqual(sessions.logged_in_users(run=run), self.expected())

    @mock.patch.object(sessions.log, "warning")
    def test_both_sources_fail(self, warning):
        run = fake_run({"loginctl list-sessions": FileNotFoundError(), "who": FileNotFoundError()})
        self.assertEqual(sessions.logged_in_users(run=run), [])
        warning.assert_called_once()


class DedupeTest(unittest.TestCase):
    def test_counts_and_order(self):
        result = sessions.dedupe([
            ("bob", "ssh", "203.0.113.9"), ("alice", "ssh", "203.0.113.7"),
            ("alice", "desktop", None), ("bob", "ssh", "203.0.113.9"),
        ])
        self.assertEqual(result, [
            Session("alice", "desktop", None, 1),
            Session("alice", "ssh", "203.0.113.7", 1),
            Session("bob", "ssh", "203.0.113.9", 2),
        ])

    def test_different_remotes_stay_separate(self):
        result = sessions.dedupe([("bob", "ssh", "203.0.113.9"), ("bob", "ssh", "203.0.113.10")])
        self.assertEqual(len(result), 2)


class WaitForSessionTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def test_appears_after_a_while(self):
        answers = [[], [], [Session("alice", "ssh", "203.0.113.7", 1)]]
        found = sessions.wait_for_session("alice", "203.0.113.7", lister=lambda: answers.pop(0),
                                          sleep=self.sleep, clock=self.clock)
        self.assertTrue(found)
        self.assertEqual(self.sleeps, [0.5, 0.5])

    def test_gives_up_after_timeout(self):
        found = sessions.wait_for_session("alice", lister=lambda: [], sleep=self.sleep,
                                          clock=self.clock)
        self.assertFalse(found)
        self.assertEqual(self.now, 3.0)

    def test_remote_must_match(self):
        other = [Session("alice", "ssh", "198.51.100.2", 1)]
        found = sessions.wait_for_session("alice", "203.0.113.7", timeout=1, lister=lambda: other,
                                          sleep=self.sleep, clock=self.clock)
        self.assertFalse(found)


if __name__ == "__main__":
    unittest.main()
