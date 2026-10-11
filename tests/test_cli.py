import contextlib
import io
import json
import os
from datetime import datetime, timezone
import tempfile
import unittest
from unittest import mock

from hostwatch import cli, state

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(REPO, "config.example.ini")
WEBHOOK = "https://hooks.slack.com/services/T000/B000/XXXXXXXX"
_patches = []


def setUpModule():
    # Keep the clean-shutdown marker out of /var/lib, and never query the real
    # logind / wait for sessions during tests (individual tests override these).
    state_dir = tempfile.mkdtemp()
    _patches[:] = [
        mock.patch.dict(os.environ, {state.STATE_DIR_ENV: state_dir}),
        mock.patch.object(cli.sessions, "logged_in_users", return_value=[]),
        mock.patch.object(cli.sessions, "wait_for_session", return_value=True),
    ]
    for p in _patches:
        p.start()


def tearDownModule():
    for p in reversed(_patches):
        p.stop()


def marker_path():
    return os.path.join(os.environ[state.STATE_DIR_ENV], state.MARKER)


def set_marker(present):
    if present:
        open(marker_path(), "w").close()
    elif os.path.exists(marker_path()):
        os.remove(marker_path())


def run(argv, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv, **kw) if kw else cli.main(argv)
    return code, out.getvalue()


class LoginTypeTest(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(cli.login_type("open_session", "sshd"), "SSH")
        self.assertEqual(cli.login_type("open_session", "login"), "TTY")
        for service in ("gdm-password", "gdm-autologin", "lightdm", "sddm"):
            self.assertEqual(cli.login_type("open_session", service), "Graphical")

    def test_ignored_services(self):
        for service in ("su", "sudo", "systemd-user", "cron", "gdm-launch-environment",
                        "polkit-1", "", None):
            self.assertIsNone(cli.login_type("open_session", service), service)

    def test_close_session_ignored(self):
        self.assertIsNone(cli.login_type("close_session", "sshd"))
        self.assertIsNone(cli.login_type(None, "sshd"))


@mock.patch.object(cli.log, "warning")
@mock.patch.object(cli.netinfo, "hostname", return_value="my-pc")
class DryRunTest(unittest.TestCase):
    def test_test_dry_run_with_example(self, _host, _warning):
        with mock.patch.object(cli.slack, "post") as post:
            code, out = run(["test", "--dry-run", "--config", EXAMPLE])
        self.assertEqual(code, 0)
        post.assert_not_called()
        payload = json.loads(out)
        self.assertTrue(payload["text"].startswith("my-pc · Test message at "))
        self.assertEqual(payload["blocks"][0]["text"]["text"], ":desktop_computer: my-pc · Test")
        self.assertIn("*Local IP*", out)
        self.assertIn("_No users logged in_", out)

    def test_options_before_subcommand(self, _host, _warning):
        code, out = run(["--dry-run", "--config", EXAMPLE, "test"])
        self.assertEqual(code, 0)
        self.assertIn("blocks", json.loads(out))

    @mock.patch.object(cli.netinfo, "local_addresses", return_value=[("enp3s0", "10.0.0.5")])
    def test_boot_dry_run(self, _ips, _host, _warning):
        set_marker(True)
        # Building the boot message must not touch the network.
        with mock.patch.object(cli.slack, "post") as post, \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used")), \
                mock.patch("socket.create_connection", side_effect=AssertionError("network used")):
            code, out = run(["boot", "--dry-run", "--config", EXAMPLE])
        self.assertEqual(code, 0)
        post.assert_not_called()
        payload = json.loads(out)
        self.assertTrue(payload["text"].startswith("my-pc · Booted at "))
        self.assertEqual(payload["blocks"][0]["text"]["text"], ":desktop_computer: my-pc · Boot")
        self.assertIn("enp3s0: 10.0.0.5", out)
        labels = [f["text"].split("\n")[0] for f in payload["blocks"][1]["fields"]]
        self.assertEqual(labels, ["*Time*", "*Kernel boot*", "*Local IP*", "*Users*"])

    def test_login_dry_run_ssh(self, _host, _warning):
        env = {"PAM_TYPE": "open_session", "PAM_SERVICE": "sshd", "PAM_USER": "alice",
               "PAM_RHOST": "203.0.113.7", "PAM_TTY": "ssh"}
        args = cli.build_parser().parse_args(["login", "--dry-run", "--config", EXAMPLE])
        out = io.StringIO()
        detach, wait = mock.Mock(), mock.Mock()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.run_login(args, environ=env, detach=detach, wait=wait), 0)
        detach.assert_not_called()
        wait.assert_not_called()  # dry runs don't wait for logind
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["text"].startswith(
            "my-pc · alice logged in via SSH from 203.0.113.7 at "))

    def test_login_dry_run_without_config_uses_defaults(self, _host, warning):
        env = {"PAM_TYPE": "open_session", "PAM_SERVICE": "login", "PAM_USER": "bob",
               "PAM_TTY": "/dev/tty3"}
        missing = os.path.join(tempfile.gettempdir(), "no-such-hostwatch.ini")
        args = cli.build_parser().parse_args(["login", "--dry-run", "--config", missing])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.run_login(args, environ=env)
        self.assertIn("/dev/tty3", out.getvalue())
        warning.assert_called()


@mock.patch.object(cli.netinfo, "hostname", return_value="my-pc")
class SendTest(unittest.TestCase):
    def config_file(self):
        fd, path = tempfile.mkstemp(suffix=".ini")
        with os.fdopen(fd, "w") as fh:
            fh.write(f"[slack]\nwebhook_url = {WEBHOOK}\n")
        self.addCleanup(os.remove, path)
        return path

    @mock.patch.object(cli.log, "error")
    def test_placeholder_config_logs_and_sends_nothing(self, error, _host):
        with mock.patch.object(cli.slack, "post") as post:
            self.assertEqual(cli.main(["boot", "--config", EXAMPLE]), 0)
        post.assert_not_called()
        self.assertIn("webhook not configured", error.call_args.args[0])

    def test_test_command_exit_status(self, _host):
        path = self.config_file()
        with mock.patch.object(cli.slack, "post", return_value=True) as post:
            self.assertEqual(cli.main(["test", "--config", path]), 0)
        self.assertEqual(post.call_args.args[0], WEBHOOK)
        with mock.patch.object(cli.slack, "post", return_value=False):
            self.assertEqual(cli.main(["test", "--config", path]), 1)

    def test_boot_uses_boot_schedule_and_exits_zero_on_failure(self, _host):
        with mock.patch.object(cli.slack, "post", return_value=False) as post:
            self.assertEqual(cli.main(["boot", "--config", self.config_file()]), 0)
        self.assertEqual(post.call_args.args[2], cli.slack.BOOT_DELAYS)
        self.assertTrue(callable(post.call_args.args[1]))

    def test_login_ignored_service_does_nothing(self, _host):
        args = cli.build_parser().parse_args(["login", "--config", self.config_file()])
        detach = mock.Mock()
        with mock.patch.object(cli.slack, "post") as post:
            cli.run_login(args, environ={"PAM_TYPE": "open_session", "PAM_SERVICE": "sudo"},
                          detach=detach)
        detach.assert_not_called()
        post.assert_not_called()

    def test_login_parent_returns_without_sending(self, _host):
        args = cli.build_parser().parse_args(["login", "--config", self.config_file()])
        env = {"PAM_TYPE": "open_session", "PAM_SERVICE": "sshd", "PAM_USER": "alice"}
        with mock.patch.object(cli.slack, "post") as post:
            self.assertEqual(cli.run_login(args, environ=env, detach=lambda: False), 0)
        post.assert_not_called()

    def test_login_child_sends_with_login_schedule(self, _host):
        args = cli.build_parser().parse_args(["login", "--config", self.config_file()])
        env = {"PAM_TYPE": "open_session", "PAM_SERVICE": "gdm-password", "PAM_USER": "carol"}
        wait = mock.Mock(return_value=True)
        with mock.patch.object(cli.slack, "post", return_value=True) as post:
            self.assertEqual(cli.run_login(args, environ=env, detach=lambda: True, wait=wait), 0)
        wait.assert_called_once_with("carol", None)
        self.assertEqual(post.call_args.args[2], cli.slack.LOGIN_DELAYS)
        build = post.call_args.args[1]
        self.assertTrue(callable(build))  # rebuilt on each attempt
        self.assertIn("carol logged in via Graphical", build()["text"])

    def test_login_ssh_waits_for_matching_session_and_sends_anyway(self, _host):
        args = cli.build_parser().parse_args(["login", "--config", self.config_file()])
        env = {"PAM_TYPE": "open_session", "PAM_SERVICE": "sshd", "PAM_USER": "alice",
               "PAM_RHOST": "203.0.113.7"}
        wait = mock.Mock(return_value=False)  # session never appeared
        with mock.patch.object(cli.slack, "post", return_value=True) as post:
            cli.run_login(args, environ=env, detach=lambda: True, wait=wait)
        wait.assert_called_once_with("alice", "203.0.113.7")
        post.assert_called_once()

    def test_login_users_come_from_logind_at_send_time(self, _host):
        args = cli.build_parser().parse_args(["login", "--config", self.config_file()])
        env = {"PAM_TYPE": "open_session", "PAM_SERVICE": "sshd", "PAM_USER": "alice",
               "PAM_RHOST": "203.0.113.7"}
        live = [cli.sessions.Session("alice", "ssh", "203.0.113.7", 1)]
        with mock.patch.object(cli.slack, "post", return_value=True) as post, \
                mock.patch.object(cli.sessions, "logged_in_users", return_value=live):
            cli.run_login(args, environ=env, detach=lambda: True, wait=mock.Mock())
            payload = post.call_args.args[1]()
        self.assertIn("alice · ssh from 203.0.113.7", str(payload))

    @mock.patch.object(cli.log, "error")
    def test_login_child_swallows_errors(self, error, _host):
        args = cli.build_parser().parse_args(["login", "--config", self.config_file()])
        env = {"PAM_TYPE": "open_session", "PAM_SERVICE": "sshd", "PAM_USER": "alice"}
        with mock.patch.object(cli.slack, "post", side_effect=RuntimeError("boom")):
            self.assertEqual(cli.run_login(args, environ=env, detach=lambda: True), 0)
        self.assertIn("unexpected error", error.call_args.args[0])


def write_config():
    fd, path = tempfile.mkstemp(suffix=".ini")
    with os.fdopen(fd, "w") as fh:
        fh.write(f"[slack]\nwebhook_url = {WEBHOOK}\n")
    return path


@mock.patch.object(cli.netinfo, "hostname", return_value="my-pc")
@mock.patch.object(cli.netinfo, "local_addresses", return_value=[("enp3s0", "192.168.1.20")])
@mock.patch.object(cli.log, "warning")
class BootMarkerTest(unittest.TestCase):
    def setUp(self):
        self.config = write_config()
        self.addCleanup(os.remove, self.config)

    def boot(self, *extra):
        with mock.patch.object(cli.slack, "post", return_value=True) as post:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cli.main(["boot", "--config", self.config, *extra])
        return post, out.getvalue()

    def test_clean_previous_shutdown(self, _warning, _ips, _host):
        set_marker(True)
        post, _ = self.boot()
        self.assertNotIn("not clean", str(post.call_args.args[1]()))
        self.assertFalse(os.path.exists(marker_path()))

    def test_unclean_previous_shutdown(self, warning, _ips, _host):
        set_marker(False)
        post, _ = self.boot()
        payload = post.call_args.args[1]()
        self.assertIn("Previous shutdown was not clean (power loss or crash?)", str(payload))
        self.assertIn("previous shutdown was not clean", payload["text"])
        warning.assert_called_with("boot: previous shutdown was not clean")

    @mock.patch.object(cli.log, "error")
    def test_config_error_still_consumes_marker(self, _error, _warning, _ips, _host):
        set_marker(True)
        with mock.patch.object(cli.slack, "post") as post:
            cli.main(["boot", "--config", EXAMPLE])  # placeholder webhook -> config error
        post.assert_not_called()
        self.assertFalse(os.path.exists(marker_path()))

    def test_dry_run_leaves_marker(self, _warning, _ips, _host):
        set_marker(True)
        post, out = self.boot("--dry-run")
        post.assert_not_called()
        self.assertTrue(os.path.exists(marker_path()))
        self.assertNotIn("not clean", out)


@mock.patch.object(cli.netinfo, "hostname", return_value="my-pc")
@mock.patch.object(cli.netinfo, "local_addresses", return_value=[("enp3s0", "192.168.1.20")])
@mock.patch.object(cli.netinfo, "shutdown_kind", return_value="Rebooting")
@mock.patch.object(cli.timefmt, "uptime_seconds", return_value=5 * 3600 + 12 * 60)
class ShutdownCommandTest(unittest.TestCase):
    def setUp(self):
        self.config = write_config()
        self.addCleanup(os.remove, self.config)
        set_marker(False)

    @mock.patch.object(cli.log, "info")
    def test_not_a_system_shutdown(self, info, *_):
        with mock.patch.object(cli.netinfo, "system_stopping", return_value=False), \
                mock.patch.object(cli.slack, "post") as post:
            self.assertEqual(cli.main(["shutdown", "--config", self.config]), 0)
        post.assert_not_called()
        self.assertFalse(os.path.exists(marker_path()))
        info.assert_called_with("shutdown: not a system shutdown, skipping")

    def test_marks_clean_before_sending_once(self, *_):
        seen = {}

        def post(*args, **kwargs):
            seen["marker_existed"] = os.path.exists(marker_path())
            seen["args"], seen["kwargs"] = args, kwargs
            return True

        with mock.patch.object(cli.netinfo, "system_stopping", return_value=True), \
                mock.patch.object(cli.slack, "post", side_effect=post) as mocked:
            self.assertEqual(cli.main(["shutdown", "--config", self.config]), 0)
        mocked.assert_called_once()
        self.assertTrue(seen["marker_existed"])
        self.assertEqual(seen["args"][2], ())
        self.assertEqual(seen["kwargs"]["timeout"], 5)
        payload = seen["args"][1]
        self.assertEqual(payload["text"].split(" at ")[0], "my-pc · Rebooting")
        self.assertEqual(payload["blocks"][0]["text"]["text"],
                         ":desktop_computer: my-pc · Rebooting")
        self.assertIn("up 5 h 12 min", payload["text"])
        self.assertIn("enp3s0: 192.168.1.20", str(payload))

    def test_failed_delivery_still_exits_zero(self, *_):
        with mock.patch.object(cli.netinfo, "system_stopping", return_value=True), \
                mock.patch.object(cli.slack, "post", return_value=False):
            self.assertEqual(cli.main(["shutdown", "--config", self.config]), 0)
        self.assertTrue(os.path.exists(marker_path()))

    @mock.patch.object(cli.log, "error")
    def test_unexpected_error_still_exits_zero(self, error, *_):
        with mock.patch.object(cli.netinfo, "system_stopping", return_value=True), \
                mock.patch.object(cli.slack, "post", side_effect=RuntimeError("boom")):
            self.assertEqual(cli.main(["shutdown", "--config", self.config]), 0)
        self.assertTrue(os.path.exists(marker_path()))
        self.assertIn("unexpected error", error.call_args.args[0])

    def test_dry_run_prints_without_marking(self, *_):
        with mock.patch.object(cli.netinfo, "system_stopping") as stopping, \
                mock.patch.object(cli.slack, "post") as post:
            code, out = run(["shutdown", "--dry-run", "--config", EXAMPLE])
        self.assertEqual(code, 0)
        stopping.assert_not_called()
        post.assert_not_called()
        self.assertFalse(os.path.exists(marker_path()))
        self.assertTrue(json.loads(out)["text"].startswith("my-pc · Rebooting at "))


@mock.patch.object(cli.netinfo, "hostname", return_value="my-pc")
class DeliveryPolicyTest(unittest.TestCase):
    def test_boot_and_login_keep_schedule_and_default_timeout(self, _host):
        path = write_config()
        self.addCleanup(os.remove, path)
        set_marker(True)
        with mock.patch.object(cli.slack, "post", return_value=True) as post, \
                mock.patch.object(cli.netinfo, "local_addresses", return_value=[]):
            cli.main(["boot", "--config", path])
        self.assertEqual(post.call_args.args[2], cli.slack.BOOT_DELAYS)
        self.assertEqual(post.call_args.kwargs["timeout"], cli.slack.TIMEOUT)
        args = cli.build_parser().parse_args(["login", "--config", path])
        env = {"PAM_TYPE": "open_session", "PAM_SERVICE": "sshd", "PAM_USER": "alice"}
        with mock.patch.object(cli.slack, "post", return_value=True) as post:
            cli.run_login(args, environ=env, detach=lambda: True)
        self.assertEqual(post.call_args.args[2], cli.slack.LOGIN_DELAYS)
        self.assertEqual(post.call_args.kwargs["timeout"], cli.slack.TIMEOUT)



@mock.patch.object(cli.netinfo, "hostname", return_value="office-pc")
@mock.patch.object(cli.netinfo, "local_addresses", return_value=[("enp3s0", "192.168.1.20")])
class IdentityTest(unittest.TestCase):
    def test_machine_name_and_users_in_every_command(self, _ips, _host):
        fd, path = tempfile.mkstemp(suffix=".ini")
        with os.fdopen(fd, "w") as fh:
            fh.write(f"[slack]\nwebhook_url = {WEBHOOK}\n[display]\nmachine_name = Office PC\n")
        self.addCleanup(os.remove, path)
        users = [cli.sessions.Session("alice", "desktop", None, 1),
                 cli.sessions.Session("alice", "ssh", "203.0.113.7", 1)]
        set_marker(True)
        payloads = []

        def post(url, payload, *a, **kw):
            payloads.append(payload() if callable(payload) else payload)
            return True

        env = {"PAM_TYPE": "open_session", "PAM_SERVICE": "sshd", "PAM_USER": "alice",
               "PAM_RHOST": "203.0.113.7"}
        with mock.patch.object(cli.slack, "post", side_effect=post), \
                mock.patch.object(cli.sessions, "logged_in_users", return_value=users), \
                mock.patch.object(cli.netinfo, "system_stopping", return_value=True), \
                mock.patch.object(cli.netinfo, "shutdown_kind", return_value="Shutting down"):
            cli.main(["test", "--config", path])
            cli.main(["boot", "--config", path])
            cli.main(["shutdown", "--config", path])
            cli.run_login(cli.build_parser().parse_args(["login", "--config", path]),
                          environ=env, detach=lambda: True, wait=mock.Mock())
        self.assertEqual(len(payloads), 4)
        for payload in payloads:
            self.assertTrue(payload["text"].startswith("Office PC (office-pc) · "), payload["text"])
            self.assertTrue(payload["blocks"][0]["text"]["text"].startswith(
                ":desktop_computer: Office PC (office-pc) · "))
            body = str(payload)
            self.assertIn("enp3s0: 192.168.1.20", body)
            self.assertIn("alice · desktop", body)
            self.assertIn("alice · ssh from 203.0.113.7", body)



TOP = [cli.processes.Row(2412, "alice", 98.0, 3.1, "yes")]


@mock.patch.object(cli.netinfo, "hostname", return_value="office-pc")
@mock.patch.object(cli.processes, "top_processes", return_value=TOP)
@mock.patch.object(cli.timefmt, "uptime_seconds", return_value=3 * 3600 + 20)
@mock.patch.object(cli.timefmt, "kernel_boot_time",
                   return_value=datetime(2026, 10, 11, 7, 14, 30, tzinfo=timezone.utc))
class HeartbeatCommandTest(unittest.TestCase):
    def config(self, extra=""):
        fd, path = tempfile.mkstemp(suffix=".ini")
        with os.fdopen(fd, "w") as fh:
            fh.write(f"[slack]\nwebhook_url = {WEBHOOK}\n{extra}")
        self.addCleanup(os.remove, path)
        return path

    def test_sends_single_attempt_with_ipv4_only(self, *_):
        path = self.config("[boot]\ninclude_ipv6 = true\n[display]\ntimezone = Europe/Warsaw\n")
        with mock.patch.object(cli.netinfo, "local_addresses",
                               return_value=[("enp3s0", "192.168.1.20")]) as addrs, \
                mock.patch.object(cli.slack, "post", return_value=True) as post:
            self.assertEqual(cli.main(["heartbeat", "--config", path]), 0)
        self.assertFalse(addrs.call_args.args[1])  # IPv6 never requested, despite the config
        post.assert_called_once()
        self.assertEqual(post.call_args.args[2], ())
        self.assertEqual(post.call_args.kwargs["timeout"], 5)
        payload = post.call_args.args[1]
        self.assertEqual(payload["text"],
                         "office-pc · Alive, up 3 h 0 min (since 2026-10-11 09:14 CEST)")
        self.assertEqual(payload["blocks"][0]["text"]["text"],
                         ":desktop_computer: office-pc · Heartbeat")
        self.assertIn("2412 alice     98.0   3.1  yes", str(payload))

    @mock.patch.object(cli.log, "info")
    def test_disabled_sends_nothing(self, info, *_):
        path = self.config("[heartbeat]\nenabled = false\n")
        with mock.patch.object(cli.slack, "post") as post:
            self.assertEqual(cli.main(["heartbeat", "--config", path]), 0)
        post.assert_not_called()
        info.assert_called_with("heartbeat: disabled in config, skipping")

    @mock.patch.object(cli.log, "error")
    def test_invalid_interval_sends_nothing(self, error, *_):
        path = self.config("[heartbeat]\ninterval_minutes = hourly\n")
        with mock.patch.object(cli.slack, "post") as post:
            self.assertEqual(cli.main(["heartbeat", "--config", path]), 0)
        post.assert_not_called()
        self.assertIn("interval_minutes", error.call_args.args[0])

    def test_failed_delivery_exits_zero(self, *_):
        with mock.patch.object(cli.netinfo, "local_addresses", return_value=[]), \
                mock.patch.object(cli.slack, "post", return_value=False):
            self.assertEqual(cli.main(["heartbeat", "--config", self.config()]), 0)

    @mock.patch.object(cli.log, "error")
    def test_unexpected_error_exits_zero(self, error, *_):
        with mock.patch.object(cli.netinfo, "local_addresses", side_effect=RuntimeError("boom")):
            self.assertEqual(cli.main(["heartbeat", "--config", self.config()]), 0)
        self.assertIn("unexpected error", error.call_args.args[0])

    @mock.patch.object(cli.log, "warning")
    def test_dry_run_prints(self, _warning, *_):
        with mock.patch.object(cli.netinfo, "local_addresses", return_value=[]), \
                mock.patch.object(cli.slack, "post") as post:
            code, out = run(["heartbeat", "--dry-run", "--config", EXAMPLE])
        self.assertEqual(code, 0)
        post.assert_not_called()
        self.assertIn("Top processes", out)

    def test_heartbeat_interval_helper(self, *_):
        code, out = run(["heartbeat-interval", "--config", self.config()])
        self.assertEqual((code, out.strip()), (0, "60"))
        code, out = run(["heartbeat-interval", "--config",
                         self.config("[heartbeat]\ninterval_minutes = 15\n")])
        self.assertEqual((code, out.strip()), (0, "15"))
        with mock.patch.object(cli.log, "error") as error:
            code, out = run(["heartbeat-interval", "--config",
                             self.config("[heartbeat]\ninterval_minutes = 1\n")])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("interval_minutes", error.call_args.args[0])

    def test_heartbeat_interval_works_with_placeholder_webhook(self, *_):
        # install.sh runs this before the user may have set a webhook.
        code, out = run(["heartbeat-interval", "--config", EXAMPLE])
        self.assertEqual((code, out.strip()), (0, "60"))

    def test_helper_hidden_from_help(self, *_):
        helptext = cli.build_parser().format_help()
        self.assertIn("heartbeat", helptext)
        self.assertNotIn("heartbeat-interval", helptext)


if __name__ == "__main__":
    unittest.main()
