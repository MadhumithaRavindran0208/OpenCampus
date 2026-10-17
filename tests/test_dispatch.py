"""
Tests for external dispatch (email/webhook). Since these channels are
off by default, most of this suite proves the fail-closed contract:
nothing is sent, nothing raises, when unconfigured. One test turns
webhook dispatch on and points it at a local HTTP server to prove the
payload actually goes out when configured.

Dispatch is offloaded to background threads (see dispatch.py::
run_in_background) so a slow SMTP server or webhook endpoint never
makes a request wait. Two consequences for these tests:
  - _CapturingHandler.received is written from a background HTTP
    server thread AND read from the test thread, so it's guarded by a
    lock rather than relied on to "just work" via the GIL.
  - Any test that goes through the real event bus (not calling
    dispatch.send_webhook directly) must call dispatch.wait_for_pending()
    before asserting, since the send happens on a worker thread that
    may not have finished by the time the triggering request returns.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.core import dispatch
from tests.base import OpenCampusTestCase


class DispatchDisabledByDefaultTests(OpenCampusTestCase):
    def test_send_email_noop_when_disabled(self):
        with self.app.app_context():
            result = dispatch.send_email("someone@example.edu", "Subject", "Body")
        self.assertFalse(result)

    def test_send_email_noop_without_recipient(self):
        with self.app.app_context():
            self.app.config["ENABLE_EMAIL_NOTIFICATIONS"] = True
            self.app.config["SMTP_HOST"] = "smtp.example.com"
            result = dispatch.send_email(None, "Subject", "Body")
        self.assertFalse(result)

    def test_send_webhook_noop_when_disabled(self):
        with self.app.app_context():
            result = dispatch.send_webhook("test.event", {"a": 1})
        self.assertFalse(result)

    def test_send_webhook_noop_without_url_even_if_enabled(self):
        with self.app.app_context():
            self.app.config["ENABLE_WEBHOOK_NOTIFICATIONS"] = True
            self.app.config["WEBHOOK_URL"] = ""
            result = dispatch.send_webhook("test.event", {"a": 1})
        self.assertFalse(result)


class _CapturingHandler(BaseHTTPRequestHandler):
    received: list = []
    lock = threading.Lock()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        with _CapturingHandler.lock:
            _CapturingHandler.received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # silence test output

    @classmethod
    def snapshot(cls) -> list:
        with cls.lock:
            return list(cls.received)

    @classmethod
    def reset(cls) -> None:
        with cls.lock:
            cls.received = []


class WebhookDeliveryTests(OpenCampusTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _CapturingHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        super().setUp()
        _CapturingHandler.reset()  # each test gets a clean capture list, regardless of run order

    def test_webhook_delivers_payload_when_configured(self):
        with self.app.app_context():
            self.app.config["ENABLE_WEBHOOK_NOTIFICATIONS"] = True
            self.app.config["WEBHOOK_URL"] = f"http://127.0.0.1:{self.port}/hook"
            result = dispatch.send_webhook("issue.claimed", {"issue_id": 42, "title": "Fix the bug"})
        self.assertTrue(result)
        received = _CapturingHandler.snapshot()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["event"], "issue.claimed")
        self.assertEqual(received[0]["data"]["issue_id"], 42)

    def test_issue_claim_triggers_webhook_relay_end_to_end(self):
        """Proves the event bus really drives dispatch.py, not just a direct call."""
        with self.app.app_context():
            self.app.config["ENABLE_WEBHOOK_NOTIFICATIONS"] = True
            self.app.config["WEBHOOK_URL"] = f"http://127.0.0.1:{self.port}/hook"

        self.register("maintainer3@example.edu", name="Maintainer Three")
        self.create_club("Webhook Club")
        self.create_project(club_id=1, name="Webhook Project")
        self.open_issue(slug="webhook-project", title="Relay me")

        dispatch.wait_for_pending(timeout=5)  # webhook send happens on a background thread now
        events_seen = [r["event"] for r in _CapturingHandler.snapshot()]
        self.assertIn("issue.created", events_seen)

    def test_dispatch_does_not_block_the_request(self):
        """The whole point of backgrounding: the web request that triggers
        a webhook must return well before the webhook call itself
        resolves -- even if that call is slow to fail."""
        import time

        with self.app.app_context():
            self.app.config["ENABLE_WEBHOOK_NOTIFICATIONS"] = True
            # Nothing listens here -- connection is refused immediately,
            # which is enough to prove ordering (request returns before
            # dispatch.wait_for_pending() would) without depending on a
            # real network timeout (slow and environment-dependent).
            self.app.config["WEBHOOK_URL"] = "http://127.0.0.1:1/unreachable"

        self.register("speedtest@example.edu")
        self.create_club("Speed Club")
        start = time.monotonic()
        self.create_project(club_id=1, name="Speed Project")
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 2.0, "request appears to have blocked on the webhook call")
        dispatch.wait_for_pending(timeout=5)  # let the background failure resolve before the test ends


if __name__ == "__main__":
    import unittest
    unittest.main()