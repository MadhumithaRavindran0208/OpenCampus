# OpenCampus OSS

A campus collaboration platform where student projects, documentation, and
mentorship survive graduating batches. Built from the OpenCampus OSS Product
Bible's MVP scope: authentication, clubs, projects, issue tracking,
documentation, mentorship requests, announcements, notifications, search, and
an administration portal.

## Quick start

Requires only Python 3.10+ and Flask -- no database server, no Node, no
build step.

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Optional: populate demo data (clubs, projects, issues, docs, mentorships)
python scripts/seed_data.py

python run.py
```

Then open **http://localhost:5000**.

If you ran the seed script, sign in with any of these (password for all is
`password123`):

| Email | Role |
|---|---|
| `admin@opencampus.dev` | platform admin |
| `arjun.k@opencampus.dev` | project owner / club admin |
| `mentor.das@opencampus.dev` | mentor |
| `student.meera@opencampus.dev` | student contributor |

Or just register your own account from the UI -- self-registration is on by
default (`OPENCAMPUS_ALLOW_SIGNUP=true`, see `.env.example`).

## Running the tests

```bash
python -m unittest discover -s tests -v
```

20 tests cover registration/auth, club and project creation with slug
disambiguation, the full issue lifecycle (open → claim → close), the event
bus actually notifying maintainers and logging contributions, mentorship
request/accept, and admin RBAC. All run against a throwaway temp database, so
they never touch your real data.

## What's implemented (MVP scope from the Product Bible)

| Module | What it does |
|---|---|
| **Auth** | Registration, login, sessions, public profiles with contribution history |
| **Clubs** | Create/join clubs, member lists, club-level admin role |
| **Projects** | Create projects under a club, difficulty/status tags, membership, **ownership transfer** workflow |
| **Issues** | Open, claim, comment, change status (open → claimed → in_review → done/closed) |
| **Docs** | Per-project documentation pages (README, onboarding guide, architecture notes, general guides) |
| **Mentorship** | Students request mentorship on a project; mentors/maintainers accept, decline, or complete it |
| **Announcements** | Platform-wide or club-scoped announcements |
| **Notifications** | In-app notification feed, driven entirely by the event bus (see below) |
| **Search** | Unified keyword search across projects, issues, docs, and clubs |
| **Admin** | Platform stats, user role/activation management, ownership-transfer approval, top contributors, "projects needing attention" |

## Project layout

```
app/
  core/            shared services every module depends on, nothing depends on a module
    config.py      every tunable value and feature flag, in one place
    db.py          the only file that talks to sqlite3 directly
    events.py      the event bus (see "How modules stay decoupled" below)
    listeners.py   the only file that wires notifications/analytics to events
    security.py    password hashing, session auth, RBAC decorators
    utils.py       slugs, notify(), log_contribution(), pagination
  blueprints/      one folder per module: auth, clubs, projects, issues,
                   docs, mentorship, announcements, notifications, search, admin
    <module>/service.py   business logic, plain functions, fully testable
    <module>/routes.py    thin Flask views that call service.py
  templates/       Jinja2 templates, one subfolder per module
  static/css/      a small hand-written design system (no framework, no build step)
migrations/        numbered .sql files, applied automatically on startup
scripts/seed_data.py   realistic demo data
tests/             unittest suite (no external test runner needed)
```

## How modules stay decoupled (why you can extend this without a rewrite)

This was a specific requirement: the platform should always have room for
alteration without replanning or rebuilding core concepts. Two decisions
make that true:

1. **No module imports another module's internals.** `issues/service.py`
   never imports anything from `notifications/`. Instead, when an issue is
   claimed or closed, it calls `events.emit(...)`. `app/core/listeners.py`
   is the *only* file that reacts to that event and decides what happens
   (create a notification, log a contribution). **To add a new reaction to
   something that already happens, you edit one function in
   `listeners.py` -- nothing else.** To add a brand-new event, you emit it
   from wherever it happens and add one handler in `listeners.py`.

2. **The database is reached through one file.** `app/core/db.py` is the
   only place that imports `sqlite3`. Every blueprint calls
   `db.query()` / `db.execute()`. If this ever needs to move to Postgres,
   that's a rewrite of one file's internals, not a schema-by-schema hunt
   through ten blueprints.

Schema changes go in `migrations/000N_description.sql` -- never edit
`0001_initial_schema.sql` after it's been applied anywhere. The migration
runner (`app/core/db.py::apply_migrations`) tracks what's been applied in a
`schema_migrations` table and runs new files automatically on startup.

See **ARCHITECTURE.md** for the full set of engineering decisions (ADRs),
including *why* this is Flask + sqlite3 rather than FastAPI + Postgres, and
exactly what to change if you outgrow that choice.

## Configuration

Everything tunable lives in `app/core/config.py` and can be overridden with
environment variables -- see `.env.example`. Nothing is hardcoded elsewhere:
domain constants like issue statuses, project difficulties, and user roles
are all defined once in `Config` and referenced everywhere else.

## Known simplifications (documented on purpose, not overlooked)

- **Auth is session-cookie based, not token/JWT.** Fine for a server-rendered
  app; if you add a separate JS frontend or public API later, add token auth
  as a second path alongside sessions in `app/core/security.py` -- don't
  replace it.
- **SQLite, not Postgres.** Handles this workload fine and needs zero setup.
  `app/core/db.py` is the single seam to swap if you need to scale writes.
- **No email delivery.** Notifications are in-app only. Add an email module
  that subscribes to the same events in `listeners.py`.
- **Club approval workflow is a feature flag, not built out.** Turning on
  `OPENCAMPUS_CLUB_APPROVAL` currently does nothing yet -- it's there so the
  intended extension point is visible; wire it into `clubs/service.py`
  when needed.
