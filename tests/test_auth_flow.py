"""
Browser-realistic auth flow tests.

The shared test base disables CSRF and email verification, which hides bugs
that only appear in a real browser (e.g. a form missing its CSRF token, or a
logout that leaves the remember-me cookie alive). These tests run with both
protections ON.
"""
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.core import events
from app.blueprints.auth.routes import _safe_next_url
from app.blueprints.auth.models import User
from app.extensions import db

EMAIL = "alice.smith@gmail.com"
PASSWORD = "password123"


def _token(html: str):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        events.reset_subscribers()
        self.tmpdir = tempfile.mkdtemp()
        db_file = Path(self.tmpdir) / "t.db"
        self.app = create_app({
            "DATA_DIR": Path(self.tmpdir),
            "DATABASE_PATH": db_file,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file.as_posix()}",
            "ALLOW_SELF_REGISTRATION": True,
            "TESTING": False,
            "WTF_CSRF_ENABLED": True,
            "REQUIRE_EMAIL_VERIFICATION": True,
            "RATELIMIT_ENABLED": False,
            "MAIN_ADMIN_SECRET_CODE": "adm",
        })
        self.c = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _register(self):
        t = _token(self.c.get("/auth/register").data.decode())
        return self.c.post("/auth/register", data={
            "full_name": "Alice Smith", "email": EMAIL, "password": PASSWORD,
            "role": "student", "csrf_token": t})

    def _verify(self, register_response):
        path = re.search(r'href="http[^"]*?(/auth/verify-email/[^"]+)"',
                         register_response.data.decode()).group(1)
        return self.c.get(path)

    def _login(self, next_url=None):
        url = "/auth/login" + (f"?next={next_url}" if next_url else "")
        t = _token(self.c.get(url).data.decode())
        return self.c.post(url, data={"email": EMAIL, "password": PASSWORD, "csrf_token": t})

    def _signed_in_user(self):
        self._verify(self._register())
        self.c.get("/auth/logout")

    def test_register_form_carries_csrf_token(self):
        self.assertIsNotNone(_token(self.c.get("/auth/register").data.decode()))

    def test_register_without_csrf_is_rejected_and_with_csrf_works(self):
        r = self.c.post("/auth/register", data={
            "full_name": "A", "email": EMAIL, "password": PASSWORD, "role": "student"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._register().status_code, 200)

    def test_unverified_user_cannot_login(self):
        self._register()
        r = self._login()
        self.assertEqual(r.status_code, 200)
        self.assertIn("verify your email", r.data.decode().lower())

    def test_full_signup_verify_login_flow(self):
        self._verify(self._register())
        self.c.get("/auth/logout")
        r = self._login()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/auth/profile").status_code, 200)

    def test_logout_really_signs_out_remember_me_user(self):
        self._signed_in_user()
        self._login()
        self.assertEqual(self.c.get("/auth/profile").status_code, 200)
        self.c.get("/auth/logout")
        self.assertEqual(self.c.get("/auth/profile").status_code, 302)

    def test_login_next_is_not_an_open_redirect(self):
        self._signed_in_user()
        r = self._login(next_url="https://evil.example/")
        self.assertNotIn("evil.example", r.headers["Location"])

    def test_login_keeps_safe_next(self):
        self._signed_in_user()
        self.assertEqual(self._login(next_url="/projects/new").headers["Location"], "/projects/new")

    def test_safe_next_rejects_dangerous_targets(self):
        for bad in ("//evil.com", "/\\evil.com", "http://evil.com", "javascript:alert(1)", "", None):
            self.assertIsNone(_safe_next_url(bad), bad)
        self.assertEqual(_safe_next_url("/projects/?q=1"), "/projects/?q=1")

    def test_verify_link_hidden_from_registrant_in_production(self):
        import os
        os.environ["OPENCAMPUS_ENV"] = "production"
        try:
            r = self._register()
            self.assertNotIn("verify-email/", r.data.decode())
        finally:
            os.environ.pop("OPENCAMPUS_ENV", None)

    def test_resend_does_not_reveal_whether_account_exists(self):
        t = _token(self.c.get("/auth/resend-verification").data.decode())
        r = self.c.post("/auth/resend-verification",
                        data={"email": "nobody@example.com", "csrf_token": t})
        self.assertNotIn("No account", r.data.decode())

    def test_deactivated_user_session_is_invalidated(self):
        self._signed_in_user()
        self._login()
        with self.app.app_context():
            User.query.filter_by(email=EMAIL).first().is_active = 0
            db.session.commit()
        self.assertEqual(self.c.get("/auth/profile").status_code, 302)

    def test_authenticated_user_is_redirected_away_from_login(self):
        self._signed_in_user()
        self._login()
        self.assertEqual(self.c.get("/auth/login").status_code, 302)


if __name__ == "__main__":
    unittest.main()
