from app.core import db
from tests.base import OpenCampusTestCase


class MentorshipTests(OpenCampusTestCase):
    def test_mentorship_request_and_accept_flow(self):
        self.register("mentor@example.edu", name="Mona Mentor", role="mentor")
        self.create_club("Mentor Club")
        self.create_project(club_id=1, name="Mentored Project")

        self.client.get("/auth/logout")
        self.register("student@example.edu", name="Sam Student")
        resp = self.client.post(
            "/mentorship/mentored-project/request", data={"message": "Can you help me get started?"},
            follow_redirects=True,
        )
        self.assertIn(b"Mentorship requested", resp.data)

        self.client.get("/auth/logout")
        self.login("mentor@example.edu")

        with self.app.app_context():
            req = db.query_one("SELECT * FROM mentorship_requests WHERE message LIKE '%get started%'")
        resp = self.client.post(f"/mentorship/{req['id']}/accept", follow_redirects=True)
        self.assertIn(b"accepted", resp.data.lower())

        with self.app.app_context():
            updated = db.query_one("SELECT * FROM mentorship_requests WHERE id = ?", (req["id"],))
        self.assertEqual(updated["status"], "accepted")
        self.assertIsNotNone(updated["mentor_id"])

    def test_duplicate_mentorship_request_rejected(self):
        self.register("owner5@example.edu")
        self.create_club("Dup Club")
        self.create_project(club_id=1, name="Dup Project")
        self.client.post("/mentorship/dup-project/request", data={"message": "help"}, follow_redirects=True)
        resp = self.client.post("/mentorship/dup-project/request", data={"message": "help again"}, follow_redirects=True)
        self.assertIn(b"already have an active mentorship request", resp.data)


class AdminRBACTests(OpenCampusTestCase):
    def test_non_admin_cannot_access_admin_dashboard(self):
        self.register("regular@example.edu")
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 403)

    def test_platform_admin_can_access_dashboard(self):
        self.register("admin1@example.edu")
        with self.app.app_context():
            db.execute("UPDATE users SET role = 'platform_admin' WHERE email = 'admin1@example.edu'")
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    import unittest
    unittest.main()
