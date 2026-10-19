import os
import tempfile
import unittest
from unittest import mock

from hostwatch import config

REPO_EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config.example.ini")
WEBHOOK = "https://hooks.slack.com/services/T000/B000/XXXXXXXX"


class ConfigTest(unittest.TestCase):
    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".ini")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_only_webhook_gives_defaults(self):
        cfg = config.load(self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n"))
        self.assertEqual(cfg.webhook_url, WEBHOOK)
        self.assertEqual(cfg.skip_interfaces, config.DEFAULT_SKIP_INTERFACES)
        self.assertFalse(cfg.include_ipv6)
        self.assertEqual(cfg.timezone, "local")
        self.assertEqual(cfg.machine_name, "")

    def test_machine_name(self):
        cfg = config.load(self.write(
            f"[slack]\nwebhook_url = {WEBHOOK}\n[display]\nmachine_name =   Office PC  \n"))
        self.assertEqual(cfg.machine_name, "Office PC")
        cfg = config.load(self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n[display]\nmachine_name =\n"))
        self.assertEqual(cfg.machine_name, "")

    def test_heartbeat_defaults(self):
        cfg = config.load(self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n"))
        self.assertEqual(config.heartbeat_settings(cfg), (True, 60))
        example = config.load(REPO_EXAMPLE, require_webhook=False)
        self.assertEqual(config.heartbeat_settings(example), (True, 60))

    def test_heartbeat_values(self):
        cfg = config.load(self.write(
            f"[slack]\nwebhook_url = {WEBHOOK}\n[heartbeat]\nenabled = no\ninterval_minutes = 15\n"))
        self.assertEqual(config.heartbeat_settings(cfg), (False, 15))
        for edge in ("5", "1440"):
            cfg = config.load(self.write(
                f"[slack]\nwebhook_url = {WEBHOOK}\n[heartbeat]\ninterval_minutes = {edge}\n"))
            self.assertEqual(config.heartbeat_settings(cfg)[1], int(edge))

    def test_invalid_heartbeat_settings(self):
        for line, setting in (("interval_minutes = 1", "interval_minutes"),
                              ("interval_minutes = 1441", "interval_minutes"),
                              ("interval_minutes = hourly", "interval_minutes"),
                              ("interval_minutes = 7.5", "interval_minutes"),
                              ("enabled = sometimes", "enabled")):
            path = self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n[heartbeat]\n{line}\n")
            cfg = config.load(path)  # loading still works: boot/login are unaffected
            with self.assertRaisesRegex(config.ConfigError, setting):
                config.heartbeat_settings(cfg)

    def test_uptime_defaults(self):
        cfg = config.load(self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n"))
        self.assertEqual(config.uptime_settings(cfg), (True, 5, 90))
        example = config.load(REPO_EXAMPLE, require_webhook=False)
        self.assertEqual(config.uptime_settings(example), (True, 5, 90))

    def test_uptime_values(self):
        cfg = config.load(self.write(
            f"[slack]\nwebhook_url = {WEBHOOK}\n[uptime]\ndaily_summary_enabled = no\n"
            "last_alive_interval_minutes = 10\nretention_days = 30\n"))
        self.assertEqual(config.uptime_settings(cfg), (False, 10, 30))
        for edge in ("1", "60"):
            cfg = config.load(self.write(
                f"[slack]\nwebhook_url = {WEBHOOK}\n[uptime]\n"
                f"last_alive_interval_minutes = {edge}\n"))
            self.assertEqual(config.uptime_settings(cfg)[1], int(edge))

    def test_invalid_uptime_settings(self):
        for line, setting in (("last_alive_interval_minutes = 0", "last_alive_interval_minutes"),
                              ("last_alive_interval_minutes = 61", "last_alive_interval_minutes"),
                              ("last_alive_interval_minutes = often", "last_alive_interval_minutes"),
                              ("retention_days = 0", "retention_days"),
                              ("retention_days = never", "retention_days"),
                              ("daily_summary_enabled = sometimes", "daily_summary_enabled")):
            path = self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n[uptime]\n{line}\n")
            cfg = config.load(path)  # loading still works: boot/login are unaffected
            with self.assertRaisesRegex(config.ConfigError, setting):
                config.uptime_settings(cfg)

    def test_login_defaults(self):
        cfg = config.load(self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n"))
        self.assertEqual(config.login_settings(cfg), (frozenset(), 30))
        example = config.load(REPO_EXAMPLE, require_webhook=False)
        self.assertEqual(config.login_settings(example), (frozenset(), 30))

    def test_login_values(self):
        cfg = config.load(self.write(
            f"[slack]\nwebhook_url = {WEBHOOK}\n[login]\nignore_users = Backup, ansible,, \n"
            "cooldown_seconds = 0\n"))
        self.assertEqual(config.login_settings(cfg), (frozenset({"backup", "ansible"}), 0))

    def test_invalid_login_settings(self):
        for line in ("cooldown_seconds = -1", "cooldown_seconds = never", "cooldown_seconds = 7.5"):
            path = self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n[login]\n{line}\n")
            cfg = config.load(path)  # loading still works: boot/heartbeat are unaffected
            with self.assertRaisesRegex(config.ConfigError, "cooldown_seconds"):
                config.login_settings(cfg)

    def test_example_leaves_machine_name_unset(self):
        self.assertEqual(config.load(REPO_EXAMPLE, require_webhook=False).machine_name, "")

    def test_all_settings(self):
        cfg = config.load(self.write(
            f"[slack]\nwebhook_url = {WEBHOOK}\n"
            "[boot]\nskip_interfaces = docker, virbr\ninclude_ipv6 = yes\n"
            "[display]\ntimezone = Europe/Warsaw\n"
        ))
        self.assertEqual(cfg.skip_interfaces, ("docker", "virbr"))
        self.assertTrue(cfg.include_ipv6)
        self.assertEqual(cfg.timezone, "Europe/Warsaw")

    def test_path_resolution(self):
        with mock.patch.dict(os.environ, {config.ENV_VAR: "/etc/hostwatch-test/env.ini"}):
            self.assertEqual(config.resolve_path(), "/etc/hostwatch-test/env.ini")
            self.assertEqual(config.resolve_path("/x.ini"), "/x.ini")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config.resolve_path(), "/etc/hostwatch/config.ini")

    def test_env_override_is_read(self):
        path = self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n")
        with mock.patch.dict(os.environ, {config.ENV_VAR: path}):
            self.assertEqual(config.load().webhook_url, WEBHOOK)

    def write_bytes(self, data):
        fd, path = tempfile.mkstemp(suffix=".ini")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        self.addCleanup(os.remove, path)
        return path

    def test_byte_order_mark_is_accepted(self):
        path = self.write_bytes(b"\xef\xbb\xbf" + f"[slack]\nwebhook_url = {WEBHOOK}\n".encode())
        self.assertEqual(config.load(path).webhook_url, WEBHOOK)

    def test_invalid_utf8_is_a_config_error(self):
        path = self.write_bytes(f"[slack]\nwebhook_url = {WEBHOOK}\n"
                                "[display]\nmachine_name = Pracownia ".encode() + b"\xb3\xf3d\xbc\n")
        with self.assertRaisesRegex(config.ConfigError, "is not valid UTF-8") as ctx:
            config.load(path)
        self.assertNotIn(WEBHOOK, str(ctx.exception))

    def test_missing_file(self):
        with self.assertRaisesRegex(config.ConfigError, "cannot read config"):
            config.load(os.path.join(tempfile.gettempdir(), "does-not-exist.ini"))

    def test_example_has_placeholder_and_is_rejected(self):
        with self.assertRaisesRegex(config.ConfigError, "webhook not configured"):
            config.load(REPO_EXAMPLE)
        cfg = config.load(REPO_EXAMPLE, require_webhook=False)
        self.assertEqual(cfg.webhook_url, config.PLACEHOLDER_WEBHOOK)

    def test_missing_webhook(self):
        with self.assertRaisesRegex(config.ConfigError, "webhook not configured"):
            config.load(self.write("[display]\ntimezone = local\n"))

    def test_non_https_webhook(self):
        path = self.write("[slack]\nwebhook_url = http://hooks.slack.com/services/a/b/c\n")
        with self.assertRaisesRegex(config.ConfigError, "https://") as ctx:
            config.load(path)
        self.assertNotIn("hooks.slack.com", str(ctx.exception))

    def test_malformed_webhook_rejected_without_quoting_it(self):
        base = "https://hooks.slack.com/services/T0/B0/XYZ"
        cases = {
            "inline comment": f"{base} # prod",
            "embedded space": "https://hooks.slack.com/services/T0/B0 XYZ",
            "tab": "https://hooks.slack.com/services/T0/B0\tXYZ",
            "missing host": "https:///services/T0/B0/XYZ",
        }
        for name, value in cases.items():
            with self.subTest(name):
                path = self.write(f"[slack]\nwebhook_url = {value}\n")
                with self.assertRaises(config.ConfigError) as ctx:
                    config.load(path)
                message = str(ctx.exception)
                self.assertIn("inline comments are not supported", message)
                for part in ("hooks.slack.com", "services", "T0", "B0", "XYZ", "prod"):
                    self.assertNotIn(part, message)

    def test_unknown_timezone(self):
        path = self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n[display]\ntimezone = Mars/Base\n")
        with self.assertRaisesRegex(config.ConfigError, "unknown timezone"):
            config.load(path)

    def test_bad_boolean(self):
        path = self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n[boot]\ninclude_ipv6 = maybe\n")
        with self.assertRaisesRegex(config.ConfigError, "invalid boolean"):
            config.load(path)

    def test_unsupported_settings_are_ignored(self):
        path = self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n"
                          "[boot]\nretired_option = maybe\nretired_url = not-a-url\n")
        cfg = config.load(path)  # must not raise
        self.assertEqual(cfg.webhook_url, WEBHOOK)
        self.assertFalse(hasattr(cfg, "retired_option"))

    def test_syntax_error_does_not_leak_webhook(self):
        path = self.write(f"webhook_url = {WEBHOOK}\n")  # no section header
        with self.assertRaises(config.ConfigError) as ctx:
            config.load(path)
        self.assertNotIn(WEBHOOK, str(ctx.exception))


class MaskWebhookTest(unittest.TestCase):
    def test_scheme_host_and_last_four(self):
        masked = config.mask_webhook("https://hooks.slack.com/services/T000/B000/xyzabcd")
        self.assertEqual(masked, "https://hooks.slack.com/…abcd")
        for secret in ("T000", "B000", "xyzab"):
            self.assertNotIn(secret, masked)

    def test_not_set(self):
        for url in ("", "   ", None, config.PLACEHOLDER_WEBHOOK):
            self.assertEqual(config.mask_webhook(url), "not set")

    def test_without_host(self):
        for url in ("hooks.slack.com/services/T000/B000/xyzabcd", "https:///T000/xyzabcd",
                    "https://[T000/xyzabcd"):
            masked = config.mask_webhook(url)
            self.assertEqual(masked, "…abcd")
            self.assertNotIn("T000", masked)

    def test_short_value(self):
        self.assertEqual(config.mask_webhook("https:/"), "…ps:/")


class MissingSettingsTest(ConfigTest):
    def test_old_config_without_heartbeat(self):
        path = self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n[boot]\nskip_interfaces = docker\n"
                          "include_ipv6 = false\n[display]\ntimezone = local\n")
        self.assertEqual(config.missing_settings(path, REPO_EXAMPLE), [
            ("heartbeat", "enabled", "true"),
            ("heartbeat", "interval_minutes", "60"),
            ("uptime", "daily_summary_enabled", "true"),
            ("uptime", "last_alive_interval_minutes", "5"),
            ("uptime", "retention_days", "90"),
            ("login", "cooldown_seconds", "30"),
        ])

    def test_complete_config_reports_nothing(self):
        self.assertEqual(config.missing_settings(REPO_EXAMPLE, REPO_EXAMPLE), [])

    def test_commented_machine_name_never_reported(self):
        path = self.write(f"[slack]\nwebhook_url = {WEBHOOK}\n")
        keys = [key for _section, key, _default in config.missing_settings(path, REPO_EXAMPLE)]
        self.assertNotIn("machine_name", keys)
        self.assertIn("timezone", keys)

    def test_defaults_come_from_code(self):
        path = self.write("[display]\ntimezone = local\n")
        missing = {(s, k): d for s, k, d in config.missing_settings(path, REPO_EXAMPLE)}
        self.assertEqual(missing[("boot", "skip_interfaces")],
                         ",".join(config.DEFAULT_SKIP_INTERFACES))
        self.assertEqual(missing[("slack", "webhook_url")], "none, required")

    def test_unreadable_config(self):
        with self.assertRaises(config.ConfigError):
            config.missing_settings("/nonexistent/config.ini", REPO_EXAMPLE)


if __name__ == "__main__":
    unittest.main()
