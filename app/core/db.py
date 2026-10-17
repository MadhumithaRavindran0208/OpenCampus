"""
Data access layer.

Deliberately thin: raw SQL over sqlite3 rather than an ORM, so the whole
platform runs with zero third-party dependencies. Every module talks to
the database only through get_db() + plain SQL -- never through another
module's internals. That single rule is what makes modules swappable
and the schema evolvable through migrations instead of rewrites.

Extension point: to move to Postgres later, this is the *only* file
that needs a new implementation (e.g. swap sqlite3 for psycopg2 behind
the same get_db()/query()/execute() functions). Nothing in the
blueprints imports sqlite3 directly.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import g, current_app


def _row_factory(cursor: sqlite3.Cursor, row: tuple):
    fields = [col[0] for col in cursor.description]
    return dict(zip(fields, row))


def get_db() -> sqlite3.Connection:
    """Return a request-scoped connection, opening one if needed."""
    if "db" not in g:
        db_path = current_app.config["DATABASE_PATH"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = _row_factory
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL lets readers and a writer run concurrently instead of the
        # default journal mode's single-writer-blocks-everyone behavior --
        # this is what actually prevents "database is locked" errors once
        # more than one request hits the app at the same time. NORMAL
        # synchronous is the documented safe pairing with WAL (still
        # durable against application crashes; only an OS-level crash
        # at the wrong instant could lose the most recent commit, which
        # is an acceptable tradeoff for this workload).
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        g.db = conn
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql: str, params: tuple = ()) -> list[dict]:
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    row = get_db().execute(sql, params).fetchone()
    return row


def execute(sql: str, params: tuple = ()) -> int:
    """Run an INSERT/UPDATE/DELETE, commit, and return lastrowid."""
    conn = get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def init_app(app) -> None:
    app.teardown_appcontext(close_db)


def apply_migrations(db_path: Path, migrations_dir: Path) -> list[str]:
    """Apply any .sql files in migrations_dir not yet recorded, in filename order."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               filename TEXT PRIMARY KEY,
               applied_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    conn.commit()

    applied = {row[0] for row in conn.execute("SELECT filename FROM schema_migrations")}
    newly_applied = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in applied:
            continue
        conn.executescript(path.read_text())
        conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,))
        conn.commit()
        newly_applied.append(path.name)

    conn.close()
    return newly_applied