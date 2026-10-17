-- Backs the OPENCAMPUS_CLUB_APPROVAL feature flag. Existing clubs (and
-- new ones when the flag is off) default to 'approved' so behavior is
-- unchanged unless an admin turns the flag on.

ALTER TABLE clubs ADD COLUMN status TEXT NOT NULL DEFAULT 'approved';

CREATE INDEX IF NOT EXISTS idx_clubs_status ON clubs(status);