from app.core import db
from tests.base import OpenCampusTestCase


class ClubApprovalTests(OpenCampusTestCase):
    def _make_platform_admin(self, email):
        with self.app.app_context():
            db.execute("UPDATE users SET role = 'platform_admin' WHERE email = ?", (email,))

    def test_clubs_are_approved_by_default_when_flag_is_off(self):
        self.register("founder@example.edu")
        resp = self.create_club("Open Club")
        self.assertIn(b"created", resp.data.lower())
        with self.app.app_context():
            club = db.query_one("SELECT * FROM clubs WHERE name = 'Open Club'")
        self.assertEqual(club["status"], "approved")

    def test_club_is_pending_when_approval_required(self):
        self.app.config["REQUIRE_ADMIN_APPROVAL_FOR_CLUBS"] = True
        self.register("founder2@example.edu")
        resp = self.create_club("Pending Club")
        self.assertIn(b"awaiting admin approval", resp.data)

        with self.app.app_context():
            club = db.query_one("SELECT * FROM clubs WHERE name = 'Pending Club'")
        self.assertEqual(club["status"], "pending")

    def test_pending_club_hidden_from_public_list_but_visible_on_own_page(self):
        self.app.config["REQUIRE_ADMIN_APPROVAL_FOR_CLUBS"] = True
        self.register("founder3@example.edu")
        self.create_club("Hidden Club")

        index_resp = self.client.get("/clubs/")
        # Only check the card grid, not flash messages -- the club name
        # should not appear as a browsable club.
        self.assertNotIn(b'href="/clubs/hidden-club"', index_resp.data)

        detail_resp = self.client.get("/clubs/hidden-club")
        self.assertIn(b"awaiting admin approval", detail_resp.data)

    def test_admin_can_approve_pending_club(self):
        self.app.config["REQUIRE_ADMIN_APPROVAL_FOR_CLUBS"] = True
        self.register("founder4@example.edu")
        self.create_club("Approve Me")
        self.client.get("/auth/logout")

        self.register("admin3@example.edu")
        self._make_platform_admin("admin3@example.edu")
        self.login("admin3@example.edu")

        queue_resp = self.client.get("/admin/clubs")
        self.assertIn(b"Approve Me", queue_resp.data)

        with self.app.app_context():
            club = db.query_one("SELECT * FROM clubs WHERE name = 'Approve Me'")
        resp = self.client.post(f"/admin/clubs/{club['id']}/approve", follow_redirects=True)
        self.assertIn(b"approved", resp.data.lower())

        with self.app.app_context():
            updated = db.query_one("SELECT * FROM clubs WHERE id = ?", (club["id"],))
        self.assertEqual(updated["status"], "approved")

        index_resp = self.client.get("/clubs/")
        self.assertIn(b'href="/clubs/approve-me"', index_resp.data)

    def test_cannot_join_pending_club(self):
        self.app.config["REQUIRE_ADMIN_APPROVAL_FOR_CLUBS"] = True
        self.register("founder5@example.edu")
        self.create_club("No Join Yet")
        self.client.get("/auth/logout")

        self.register("joiner@example.edu")
        resp = self.client.post("/clubs/no-join-yet/join", follow_redirects=True)
        self.assertIn(b"isn&#39;t open to new members yet", resp.data)


if __name__ == "__main__":
    import unittest
    unittest.main()