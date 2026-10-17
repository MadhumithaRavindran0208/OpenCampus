from tests.base import OpenCampusTestCase


class AuthTests(OpenCampusTestCase):
    def test_register_creates_user_and_logs_in(self):
        resp = self.register("student1@example.edu")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Welcome to OpenCampus OSS", resp.data)

    def test_duplicate_email_rejected(self):
        self.register("dup@example.edu")
        self.client.get("/auth/logout")
        resp = self.register("dup@example.edu")
        self.assertIn(b"already exists", resp.data)

    def test_short_password_rejected(self):
        resp = self.client.post(
            "/auth/register",
            data={"full_name": "X", "email": "shortpw@example.edu", "password": "abc", "role": "student"},
            follow_redirects=True,
        )
        self.assertIn(b"at least 8 characters", resp.data)

    def test_login_wrong_password_rejected(self):
        self.register("wrongpw@example.edu")
        self.client.get("/auth/logout")
        resp = self.login("wrongpw@example.edu", password="totallywrong")
        self.assertIn(b"Incorrect email or password", resp.data)

    def test_login_required_redirects_to_login(self):
        resp = self.client.get("/mentorship/", follow_redirects=True)
        self.assertIn(b"Sign in", resp.data)

    def test_profile_update_persists(self):
        self.register("profile@example.edu", name="Pat Original")
        resp = self.client.post(
            "/auth/profile",
            data={"full_name": "Pat Updated", "bio": "I like robots.", "skills": "Python, ROS"},
            follow_redirects=True,
        )
        self.assertIn(b"Profile updated", resp.data)
        resp2 = self.client.get("/auth/profile")
        self.assertIn(b"Pat Updated", resp2.data)
        self.assertIn(b"I like robots.", resp2.data)

    def test_contact_channels_persist_and_display(self):
        self.register("contact@example.edu", name="Casey Contact")
        resp = self.client.post(
            "/auth/profile",
            data={
                "full_name": "Casey Contact", "bio": "", "skills": "",
                "contact_email": "casey.external@example.com",
                "discord_handle": "casey#1234",
                "linkedin_url": "https://linkedin.com/in/casey",
                "github_url": "https://github.com/casey",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Profile updated", resp.data)
        resp2 = self.client.get("/auth/profile")
        self.assertIn(b"casey.external@example.com", resp2.data)
        self.assertIn(b"casey#1234", resp2.data)
        self.assertIn(b"https://linkedin.com/in/casey", resp2.data)

    def test_contact_channels_optional(self):
        """A user who never sets contact fields shouldn't see broken badges."""
        resp = self.register("nocontact@example.edu", name="No Contact")
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get("/auth/profile")
        self.assertEqual(resp2.status_code, 200)

    # --- Email format validation (bugfix: registration only checked for
    # "@" being present, and contact_email had no validation at all) ---

    def test_registration_rejects_email_with_no_domain(self):
        resp = self.client.post(
            "/auth/register",
            data={"full_name": "Bad Email", "email": "justtext@", "password": "password123", "role": "student"},
            follow_redirects=True,
        )
        self.assertIn(b"valid email address", resp.data)

    def test_registration_rejects_email_with_no_tld(self):
        resp = self.client.post(
            "/auth/register",
            data={"full_name": "Bad Email", "email": "person@localhost", "password": "password123", "role": "student"},
            follow_redirects=True,
        )
        self.assertIn(b"valid email address", resp.data)

    def test_registration_rejects_email_with_spaces(self):
        resp = self.client.post(
            "/auth/register",
            data={"full_name": "Bad Email", "email": "has space@example.com", "password": "password123", "role": "student"},
            follow_redirects=True,
        )
        self.assertIn(b"valid email address", resp.data)

    def test_registration_accepts_plausible_email(self):
        resp = self.register("2503@gil.com", name="Real Enough")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Welcome to OpenCampus OSS", resp.data)

    def test_contact_email_rejects_malformed_value(self):
        """contact_email previously had zero format validation."""
        self.register("emailbug@example.edu", name="Email Bug")
        resp = self.client.post(
            "/auth/profile",
            data={"full_name": "Email Bug", "bio": "", "skills": "", "contact_email": "not-an-email"},
            follow_redirects=True,
        )
        self.assertIn(b"valid email address", resp.data)

    def test_contact_email_accepts_valid_value(self):
        self.register("emailok@example.edu", name="Email OK")
        resp = self.client.post(
            "/auth/profile",
            data={"full_name": "Email OK", "bio": "", "skills": "", "contact_email": "2503@gil.com"},
            follow_redirects=True,
        )
        self.assertIn(b"Profile updated", resp.data)
        resp2 = self.client.get("/auth/profile")
        self.assertIn(b"2503@gil.com", resp2.data)

    def test_contact_email_still_optional(self):
        self.register("emailblank@example.edu", name="Email Blank")
        resp = self.client.post(
            "/auth/profile",
            data={"full_name": "Email Blank", "bio": "", "skills": "", "contact_email": ""},
            follow_redirects=True,
        )
        self.assertIn(b"Profile updated", resp.data)

    # --- Age category (private, bracket-based) ---

    def test_age_category_persists_and_is_private(self):
        self.register("agecat@example.edu", name="Age Cat")
        resp = self.client.post(
            "/auth/profile",
            data={"full_name": "Age Cat", "bio": "", "skills": "", "age_category": "18-24"},
            follow_redirects=True,
        )
        self.assertIn(b"Profile updated", resp.data)
        own_view = self.client.get("/auth/profile")
        self.assertIn(b"18-24", own_view.data)

    def test_age_category_not_shown_on_other_users_public_profile(self):
        self.register("agecat2@example.edu", name="Age Cat Two")
        self.client.post(
            "/auth/profile",
            data={"full_name": "Age Cat Two", "bio": "", "skills": "", "age_category": "25-34"},
            follow_redirects=True,
        )
        self.client.get("/auth/logout")
        self.register("viewer@example.edu", name="Viewer")
        public_view = self.client.get("/auth/users/1")
        self.assertNotIn(b"25-34", public_view.data)

    def test_invalid_age_category_rejected(self):
        self.register("agecat3@example.edu", name="Age Cat Three")
        resp = self.client.post(
            "/auth/profile",
            data={"full_name": "Age Cat Three", "bio": "", "skills": "", "age_category": "not-a-real-bracket"},
            follow_redirects=True,
        )
        self.assertIn(b"valid age category", resp.data)

    def test_age_category_optional(self):
        resp = self.register("agecat4@example.edu", name="Age Cat Four")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    import unittest
    unittest.main()