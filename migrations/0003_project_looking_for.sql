-- Lets maintainers flag a project as urgently needing contributors before
-- graduation, and name the skills needed -- powers the "Help Wanted"
-- badge and skill-filtered search.

ALTER TABLE projects ADD COLUMN is_seeking_contributors INTEGER NOT NULL DEFAULT 0;
ALTER TABLE projects ADD COLUMN required_skills TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_projects_seeking ON projects(is_seeking_contributors);