-- Adds optional external contact channels to user profiles, so
-- maintainers and mentors can be reached outside the platform.
-- contact_email overrides the login email for external notifications
-- when set (see app/core/dispatch.py); falls back to login email
-- otherwise.

ALTER TABLE users ADD COLUMN contact_email TEXT DEFAULT '';
ALTER TABLE users ADD COLUMN discord_handle TEXT DEFAULT '';
ALTER TABLE users ADD COLUMN linkedin_url TEXT DEFAULT '';
ALTER TABLE users ADD COLUMN github_url TEXT DEFAULT '';