-- Adds an optional age *category* (bracket) to user profiles.
-- Deliberately a bracket rather than an exact age or date of birth --
-- enough for the platform's own reporting needs (e.g. distinguishing
-- undergrad-age students from older/returning students) without
-- collecting more precise personal data than that requires.

ALTER TABLE users ADD COLUMN age_category TEXT DEFAULT '';