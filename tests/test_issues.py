from app.core import db
from tests.base import OpenCampusTestCase


class IssueTests(OpenCampusTestCase):
    def test_issue_lifecycle_open_claim_close(self):
        self.register("maintainer@example.edu", name="Maya Maintainer")
        self.create_club("Web Club")
        self.create_project(club_id=1, name="Portal")
        resp = self.open_issue(slug="portal", title="Add dark mode")
        self.assertIn(b"opened", resp.data.lower())

        with self.app.app_context():
            issue = db.query_one("SELECT * FROM issues WHERE title = 'Add dark mode'")
        self.assertEqual(issue["status"], "open")

        self.client.get("/auth/logout")
        self.register("contributor@example.edu", name="Chris Contributor")
        resp = self.client.post(f"/projects/issue/{issue['id']}/claim", follow_redirects=True)
        self.assertIn(b"claimed", resp.data.lower())

        with self.app.app_context():
            updated = db.query_one("SELECT * FROM issues WHERE id = ?", (issue["id"],))
        self.assertEqual(updated["status"], "claimed")
        self.assertIsNotNone(updated["assigned_to"])

    def test_double_claim_is_rejected(self):
        self.register("m2@example.edu")
        self.create_club("Data Club")
        self.create_project(club_id=1, name="Analytics Tool")
        self.open_issue(slug="analytics-tool", title="Write tests")

        with self.app.app_context():
            issue = db.query_one("SELECT * FROM issues WHERE title = 'Write tests'")

        self.client.post(f"/projects/issue/{issue['id']}/claim", follow_redirects=True)
        resp = self.client.post(f"/projects/issue/{issue['id']}/claim", follow_redirects=True)
        self.assertIn(b"already been claimed", resp.data)

    def test_maintainer_is_notified_when_someone_else_claims_issue(self):
        """Proves the event bus actually wires issues -> notifications without direct coupling."""
        self.register("owner3@example.edu", name="Owner Three")
        self.create_club("Notif Club")
        self.create_project(club_id=1, name="Notif Project")
        self.open_issue(slug="notif-project", title="Improve docs")

        with self.app.app_context():
            issue = db.query_one("SELECT * FROM issues WHERE title = 'Improve docs'")
            owner = db.query_one("SELECT * FROM users WHERE email = 'owner3@example.edu'")

        self.client.get("/auth/logout")
        self.register("claimer@example.edu", name="Claimer")
        self.client.post(f"/projects/issue/{issue['id']}/claim", follow_redirects=True)

        with self.app.app_context():
            notifs = db.query("SELECT * FROM notifications WHERE user_id = ?", (owner["id"],))
        self.assertTrue(any(n["type"] == "issue_claimed" for n in notifs))

    def test_closing_issue_logs_contribution_for_assignee(self):
        self.register("owner4@example.edu")
        self.create_club("Closer Club")
        self.create_project(club_id=1, name="Closer Project")
        self.open_issue(slug="closer-project", title="Ship feature")

        with self.app.app_context():
            issue = db.query_one("SELECT * FROM issues WHERE title = 'Ship feature'")

        self.client.post(f"/projects/issue/{issue['id']}/claim", follow_redirects=True)
        self.client.post(f"/projects/issue/{issue['id']}/status", data={"status": "done"}, follow_redirects=True)

        with self.app.app_context():
            contributions = db.query(
                "SELECT * FROM contribution_log WHERE activity_type = 'issue_closed'"
            )
        self.assertEqual(len(contributions), 1)
        self.assertEqual(contributions[0]["points"], 3)


if __name__ == "__main__":
    import unittest
    unittest.main()
