"""Delivery to a Slack incoming webhook with retry and backoff."""
import http.client
import json
import time
import urllib.error
import urllib.request

from . import log

TIMEOUT = 10
BOOT_DELAYS = (5, 10, 20, 40, 60)
LOGIN_DELAYS = (2, 5)
SHUTDOWN_TIMEOUT = 5  # single attempt; the unit's TimeoutStopSec is the hard cap
HEARTBEAT_TIMEOUT = 5  # single attempt; a missed heartbeat is dropped, never resent


def _retryable(status):
    return status == 429 or 500 <= status < 600


def _describe(exc):
    # Never use str(request) or the URL here: the webhook is a secret.
    reason = getattr(exc, "reason", None) or exc
    return f"{type(exc).__name__}: {reason}"


def post(webhook_url, payload, delays=(), *, event="message", timeout=TIMEOUT,
         sleep=time.sleep, urlopen=urllib.request.urlopen):
    """POST ``payload`` to the webhook. Return True when Slack accepted it.

    ``payload`` is a dict or a zero-argument callable returning one; a callable
    is called again on every attempt so late network details can be picked up.
    ``delays`` are the waits between attempts, so attempts = len(delays) + 1.
    Network errors, timeouts, 429 and 5xx are retried; other 4xx are not.
    """
    attempts = len(delays) + 1
    last = "no attempt made"
    for attempt in range(1, attempts + 1):
        body = payload() if callable(payload) else payload
        request = urllib.request.Request(
            webhook_url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                response.read()
            log.info(f"{event}: delivered to Slack (attempt {attempt}/{attempts})")
            return True
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if not _retryable(exc.code):
                log.error(f"{event}: Slack rejected the message ({last}), not retrying")
                return False
        except (OSError, http.client.HTTPException) as exc:
            last = _describe(exc)
        if attempt < attempts:
            delay = delays[attempt - 1]
            log.warning(f"{event}: attempt {attempt}/{attempts} failed ({last}), retrying in {delay}s")
            sleep(delay)
    log.error(f"{event}: giving up after {attempts} attempt(s) ({last})")
    return False
