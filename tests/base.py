"""
Shared test scaffolding using Python's built-in unittest (no third-party
test runner needed -- keeps the whole project dependency-free).

Each test gets its own throwaway SQLite file so tests never interfere
with each other or with any real data.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.core import events


class OpenCampusTestCase(unittest.TestCase):
    def setUp(self):
        # create_app() -> listeners.register_all() already calls
        # events.reset_subscribers() itself (see ARCHITECTURE.md ADR-003),
        # which is what actually keeps tests isolated. This explicit call
        # is defense in depth: if that internal wiring ever changes,
        # every test creating its own app via this base class still
        # starts from a guaranteed-empty subscriber list rather than
        # silently relying on create_app()'s side effect.
        events.reset_subscribers()

        self.tmpdir = tempfile.mkdtemp()
        self.app = create_app({
            "DATA_DIR": Path(self.tmpdir),
            "DATABASE_PATH": Path(self.tmpdir) / "test.db",
            "ALLOW_SELF_REGISTRATION": True,
            "TESTING": True,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def register(self, email, name="Test User", password="password123", role="student"):
        return self.client.post(
            "/auth/register",
            data={"full_name": name, "email": email, "password": password, "role": role},
            follow_redirects=True,
        )

    def login(self, email, password="password123"):
        return self.client.post(
            "/auth/login", data={"email": email, "password": password}, follow_redirects=True
        )

    def create_club(self, name="Test Club"):
        return self.client.post(
            "/clubs/new", data={"name": name, "description": "A test club"}, follow_redirects=True
        )

    def create_project(self, club_id=1, name="Test Project", is_seeking_contributors=False, required_skills=""):
        data = {
            "club_id": club_id, "name": name, "description": "A test project",
            "tech_stack": "Python", "repo_url": "", "difficulty": "beginner",
            "required_skills": required_skills,
        }
        if is_seeking_contributors:
            data["is_seeking_contributors"] = "on"
        return self.client.post("/projects/new", data=data, follow_redirects=True)

    def open_issue(self, slug="project", title="Fix the bug"):
        return self.client.post(
            f"/projects/{slug}/issues/new",
            data={"title": title, "description": "Something is broken", "difficulty": "beginner"},
            follow_redirects=True,
        )