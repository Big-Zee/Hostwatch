import io
import json
import unittest
import urllib.error
from unittest import mock

from hostwatch import slack

WEBHOOK = "https://hooks.slack.com/services/T000/B000/SECRETSECRET"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code):
    return urllib.error.HTTPError(WEBHOOK, code, "error", {}, None)


class PostTest(unittest.TestCase):
    def setUp(self):
        self.logged = []
        for level in ("info", "warning", "error"):
            patcher = mock.patch.object(
                slack.log, level, side_effect=lambda m, lv=level: self.logged.append((lv, m))
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        self.sleeps = []

    def post(self, outcomes, delays=(1, 2, 3), payload=None):
        calls = []

        def urlopen(request, timeout):
            calls.append((request, timeout))
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return FakeResponse(b"ok")

        ok = slack.post(WEBHOOK, payload or {"text": "hi"}, delays, event="test",
                        sleep=self.sleeps.append, urlopen=urlopen)
        return ok, calls

    def assert_no_secret_logged(self):
        for _, message in self.logged:
            self.assertNotIn(WEBHOOK, message)
            self.assertNotIn("SECRET", message)

    def test_success_first_try(self):
        ok, calls = self.post([None])
        self.assertTrue(ok)
        self.assertEqual(len(calls), 1)
        request, timeout = calls[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"text": "hi"})
        self.assertEqual(timeout, slack.TIMEOUT)
        self.assertEqual(self.sleeps, [])

    def test_transient_failures_then_success(self):
        ok, calls = self.post([urllib.error.URLError("Temporary failure in name resolution"),
                               http_error(503), None])
        self.assertTrue(ok)
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.sleeps, [1, 2])
        self.assert_no_secret_logged()

    def test_429_is_retried(self):
        ok, _ = self.post([http_error(429), None])
        self.assertTrue(ok)

    def test_timeout_is_retried(self):
        ok, _ = self.post([TimeoutError("timed out"), None])
        self.assertTrue(ok)

    def test_404_is_not_retried(self):
        ok, calls = self.post([http_error(404), None])
        self.assertFalse(ok)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.sleeps, [])
        self.assertIn("HTTP 404", self.logged[-1][1])
        self.assert_no_secret_logged()

    def test_exhausted_retries_logs_error(self):
        ok, calls = self.post([urllib.error.URLError("unreachable")] * 4)
        self.assertFalse(ok)
        self.assertEqual(len(calls), 4)
        self.assertEqual(self.sleeps, [1, 2, 3])
        level, message = self.logged[-1]
        self.assertEqual(level, "error")
        self.assertIn("test: giving up after 4 attempt(s)", message)
        self.assertIn("unreachable", message)
        self.assert_no_secret_logged()

    def test_callable_payload_rebuilt_each_attempt(self):
        built = []

        def payload():
            built.append(1)
            return {"text": f"attempt {len(built)}"}

        ok, calls = self.post([urllib.error.URLError("down"), None], payload=payload)
        self.assertTrue(ok)
        self.assertEqual(json.loads(calls[1][0].data), {"text": "attempt 2"})

    def test_malformed_url_error_does_not_leak_path(self):
        # The real urlopen rejects the space before connecting; its error text quotes the URL.
        url = "https://hooks.slack.invalid/services/T0/B0/SECRETTOKEN x"
        with mock.patch("socket.create_connection", side_effect=AssertionError("network used")):
            ok = slack.post(url, {"text": "hi"}, (1,), event="test", sleep=self.sleeps.append)
        self.assertFalse(ok)
        self.assertIn("InvalidURL", self.logged[-1][1])
        for _, message in self.logged:
            self.assertNotIn("SECRETTOKEN", message)

    def test_value_error_logs_class_name_only(self):
        ok, _ = self.post([ValueError(f"unknown url type: {WEBHOOK}")], delays=())
        self.assertFalse(ok)
        self.assertIn("(ValueError)", self.logged[-1][1])
        self.assert_no_secret_logged()

    def test_non_https_url_never_reaches_urlopen(self):
        for url in ("http://hooks.slack.com/services/T0/B0/SECRET", "file:///etc/SECRET"):
            urlopen = mock.Mock()
            ok = slack.post(url, {"text": "hi"}, (1,), event="test", sleep=self.sleeps.append,
                            urlopen=urlopen)
            self.assertFalse(ok)
            urlopen.assert_not_called()
            self.assertEqual(self.logged[-1][0], "error")
        self.assertEqual(self.sleeps, [])
        self.assert_no_secret_logged()

    def test_schedules(self):
        self.assertEqual(slack.BOOT_DELAYS, (5, 10, 20, 40, 60))
        self.assertEqual(slack.LOGIN_DELAYS, (2, 5))


if __name__ == "__main__":
    unittest.main()
