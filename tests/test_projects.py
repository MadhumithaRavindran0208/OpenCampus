from tests.base import OpenCampusTestCase


class ProjectTests(OpenCampusTestCase):
    def test_create_club_makes_creator_admin(self):
        self.register("founder@example.edu")
        resp = self.create_club("Robotics Club")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Robotics Club", resp.data)

    def test_club_requires_name(self):
        self.register("founder2@example.edu")
        resp = self.create_club("")
        self.assertIn(b"required", resp.data)

    def test_create_project_requires_login(self):
        resp = self.create_project()
        self.assertIn(b"Sign in", resp.data)

    def test_create_project_makes_creator_owner(self):
        self.register("owner@example.edu")
        self.create_club("Dev Club")
        resp = self.create_project(club_id=1, name="Line Follower Bot")
        self.assertIn(b"Line Follower Bot", resp.data)
        self.assertIn(b"created", resp.data.lower())

    def test_project_slug_disambiguation(self):
        self.register("owner2@example.edu")
        self.create_club("Dev Club 2")
        self.create_project(club_id=1, name="Same Name")
        self.create_project(club_id=1, name="Same Name")
        resp = self.client.get("/projects/same-name-2")
        self.assertEqual(resp.status_code, 200)

    def test_project_search_filters_by_difficulty(self):
        self.register("owner3@example.edu")
        self.create_club("Search Club")
        self.create_project(club_id=1, name="Beginner Proj")
        resp = self.client.get("/projects/?difficulty=advanced")
        self.assertNotIn(b"Beginner Proj", resp.data)
        resp2 = self.client.get("/projects/?difficulty=beginner")
        self.assertIn(b"Beginner Proj", resp2.data)

    def test_seeking_contributors_flag_set_on_creation(self):
        self.register("owner6@example.edu")
        self.create_club("Help Club")
        resp = self.create_project(
            club_id=1, name="Needs Help Project",
            is_seeking_contributors=True, required_skills="React, PostgreSQL",
        )
        self.assertIn(b"Help Wanted", resp.data)
        self.assertIn(b"React, PostgreSQL", resp.data)

    def test_seeking_only_filter_excludes_non_seeking_projects(self):
        self.register("owner7@example.edu")
        self.create_club("Filter Club")
        self.create_project(club_id=1, name="Quiet Project", is_seeking_contributors=False)
        self.create_project(club_id=1, name="Loud Project", is_seeking_contributors=True, required_skills="Rust")

        resp = self.client.get("/projects/?seeking=1")
        self.assertIn(b"Loud Project", resp.data)
        self.assertNotIn(b"Quiet Project", resp.data)

        resp2 = self.client.get("/projects/")
        self.assertIn(b"Loud Project", resp2.data)
        self.assertIn(b"Quiet Project", resp2.data)

    def test_keyword_search_matches_required_skills(self):
        self.register("owner8@example.edu")
        self.create_club("Skill Search Club")
        self.create_project(
            club_id=1, name="Skill Matched Project",
            is_seeking_contributors=True, required_skills="Elixir",
        )
        resp = self.client.get("/projects/?q=Elixir")
        self.assertIn(b"Skill Matched Project", resp.data)

    def test_maintainer_can_toggle_help_wanted(self):
        self.register("owner9@example.edu")
        self.create_club("Toggle Club")
        self.create_project(club_id=1, name="Toggle Project")
        resp = self.client.post(
            "/projects/toggle-project/help-wanted",
            data={"is_seeking_contributors": "on", "required_skills": "Go"},
            follow_redirects=True,
        )
        self.assertIn(b"Help Wanted", resp.data)
        self.assertIn(b"Go", resp.data)

    def test_non_maintainer_cannot_toggle_help_wanted(self):
        self.register("owner10@example.edu")
        self.create_club("Locked Club")
        self.create_project(club_id=1, name="Locked Project")
        self.client.get("/auth/logout")
        self.register("intruder@example.edu")
        resp = self.client.post(
            "/projects/locked-project/help-wanted",
            data={"is_seeking_contributors": "on", "required_skills": "Go"},
        )
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    import unittest
    unittest.main()