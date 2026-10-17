# Architecture

This document records the engineering decisions behind OpenCampus OSS, in the
spirit of the Product Bible's own principle: "Record important architectural
decisions." Each ADR explains the decision, why, and — importantly — what to
do instead if the decision stops fitting.

---

## ADR-001: Flask + sqlite3 instead of FastAPI + SQLAlchemy/Postgres

**Context.** The original plan for this build was FastAPI + SQLAlchemy +
Postgres/SQLite, which is a reasonable default for a new platform. Partway
into implementation it became clear the build environment could not reach
the internet to `pip install` anything not already present.

**Decision.** Use Flask + Python's built-in `sqlite3` module — both already
available — so the entire application, including its test suite, could
actually be run and verified rather than handed over unexecuted.

**Consequences.**
- Zero third-party dependency risk: `pip install -r requirements.txt`
  installs exactly four small, stable packages (Flask, Werkzeug, Jinja2,
  itsdangerous).
- No ORM means slightly more verbose SQL in `service.py` files, but it also
  means no ORM version drift, no lazy-loading surprises, and every query is
  visible and testable as plain SQL.
- The whole test suite runs on Python's built-in `unittest` — no `pytest`
  install needed either.

**If you outgrow this:** `app/core/db.py` is the *only* file that imports
`sqlite3`. To move to Postgres, reimplement `get_db()` / `query()` /
`execute()` in that one file (e.g. with `psycopg2` or SQLAlchemy Core), and
nothing in `app/blueprints/` needs to change, because every blueprint only
ever calls `db.query(...)` / `db.execute(...)`.

---

## ADR-002: Session-cookie auth, not JWT

**Context.** The MVP is a server-rendered app (Jinja2 templates), not a
separate API consumed by a JS frontend.

**Decision.** Use Flask's signed session cookie (backed by `SECRET_KEY`) to
store the logged-in user's id. `app/core/security.py::load_logged_in_user`
runs before every request and populates `g.user`.

**Consequences.** Simple, no token refresh/expiry logic to build, works with
plain HTML forms, no CORS complexity.

**If you outgrow this:** add a second auth path (e.g. a `Bearer` token
checked against a `api_tokens` table) alongside — not instead of — the
session check in `security.py`. Routes that should accept either can check
`g.user` (set by whichever auth succeeded) without knowing which one fired.

---

## ADR-003: An in-process event bus decouples modules

**Context.** The Product Bible's core engineering principle is that modules
"operate independently while exchanging data through clearly defined
interfaces," and that features should be addable without replanning. A
platform where `issues/service.py` directly imports and calls
`notifications/service.py` (which calls `contribution_log` helpers, which
might call `admin` stats...) would violate that within a few features.

**Decision.** `app/core/events.py` provides two functions: `emit(name,
**payload)` and `subscribe(name, handler)`. Modules that cause something to
happen (an issue is claimed, a mentorship request is accepted) call `emit`
and know nothing else. `app/core/listeners.py` is the single file that
subscribes handlers and decides what happens next (create a notification,
write a contribution-log row).

**Consequences.**
- Adding a new reaction to an existing event (e.g. "also post to an activity
  feed when an issue closes") means editing one function in `listeners.py`.
  No other file changes.
- Adding a brand-new event means one `events.emit(...)` call at the source
  and one new handler in `listeners.py`.
- It's synchronous and in-process by design — no broker to run for a
  student-club-scale deployment. If this needs to survive process restarts
  or scale across workers later, swap the two functions in `events.py` for a
  real queue (Redis Streams, RQ, Celery) — the call sites in every blueprint
  don't change.
- **Gotcha this caught in testing:** because `_subscribers` is
  module-level state, calling `create_app()` more than once in the same
  process (which the test suite does, once per test) would re-register
  every handler each time, causing them to fire multiple times per event.
  `listeners.register_all()` calls `events.reset_subscribers()` first to
  keep this idempotent — see the git history / test
  `test_closing_issue_logs_contribution_for_assignee` which caught this.

---

## ADR-004: Numbered SQL migrations, not a migration framework

**Context.** Schema needs to evolve without hand-editing databases that
already have data (a running club's real projects, for instance).

**Decision.** Plain `.sql` files in `migrations/`, applied in filename order
by `app/core/db.py::apply_migrations`, tracked in a `schema_migrations`
table. Runs automatically every time `create_app()` starts — there's no
separate "remember to migrate" step.

**Consequences.** No dependency on Alembic or similar. Slightly more manual
than an ORM-integrated migration tool, but transparent: you can read exactly
what will run.

**If you outgrow this:** add Alembic (or similar) pointed at the same
`migrations/` convention, or keep this and just write more `.sql` files —
either scales fine well past a single campus deployment.

---

## ADR-005: Business logic lives in `service.py`, not in Flask routes

**Context.** Route handlers that contain business logic are hard to test
without spinning up HTTP, and hard to reuse (e.g. from the seed script or a
future CLI/admin tool).

**Decision.** Every blueprint splits into `service.py` (plain Python
functions, raise a module-specific `*Error` exception on invalid input, no
Flask imports) and `routes.py` (thin: parse the request, call `service.py`,
flash a message, redirect/render).

**Consequences.** `scripts/seed_data.py` calls the exact same
`service.create_project(...)` etc. that the web routes call — no
duplicated logic, and any bug fixed in `service.py` is fixed everywhere.
The test suite mostly exercises routes end-to-end (closer to how a user
actually uses it), but individual `service.py` functions are trivial to
unit-test in isolation if you need to.

---

## Adding a new module (worked example)

Say you want to add a "Showcase" module where finished projects get
featured. Following the existing pattern end to end:

1. `app/blueprints/showcase/service.py` — plain functions:
   `feature_project(project_id, blurb)`, `list_featured()`.
2. `app/blueprints/showcase/routes.py` — a `Blueprint`, thin views calling
   the service.
3. `app/templates/showcase/*.html` — extend `base.html` like every other
   template.
4. Register the blueprint in `app/__init__.py::create_app` (one line).
5. `migrations/0002_showcase.sql` — a new table, applied automatically.
6. If featuring should notify the project's members, add
   `events.SHOWCASE_FEATURED` as a constant, `emit()` it from
   `service.py`, and add one handler in `listeners.py`.

Nothing in `issues/`, `projects/`, or anywhere else needs to change.
