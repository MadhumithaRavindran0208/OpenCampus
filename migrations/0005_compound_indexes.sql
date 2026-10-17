-- Replaces reliance on single-column indexes for queries that always
-- filter on two columns together. SQLite can only use one index per
-- table per query (no automatic index intersection like Postgres), so
-- a compound index matching the actual WHERE clause shape is what
-- avoids a full table scan here -- the single-column indexes from
-- 0001/0003 stay in place for other query shapes that only filter on
-- one of these columns.

-- search_projects()'s "Help Wanted" filter always pairs seeking-flag
-- with status (e.g. WHERE is_seeking_contributors = 1 AND status = 'active').
CREATE INDEX IF NOT EXISTS idx_projects_seeking_status ON projects(is_seeking_contributors, status);

-- list_issues()'s per-project, per-status filtering (issue board / claim flow).
CREATE INDEX IF NOT EXISTS idx_issues_project_status ON issues(project_id, status);

-- get_public_profile() and admin listings frequently filter mentorship
-- requests and notifications by (owner, status) / (owner, is_read) together.
CREATE INDEX IF NOT EXISTS idx_mentorship_project_status ON mentorship_requests(project_id, status);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read, created_at);