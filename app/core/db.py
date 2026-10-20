"""
Database bridge and compatibility layer backed by Flask-SQLAlchemy.

Primary data access is performed using SQLAlchemy ORM models distributed in each blueprint.
This module provides db.session access and SQL text helpers for migrations and raw queries.
"""
from __future__ import annotations

import logging
from flask import current_app
from sqlalchemy import text
from app.extensions import db

logger = logging.getLogger("opencampus.db")


def get_db():
    """Return the active SQLAlchemy database session."""
    return db.session


def close_db(_exc=None) -> None:
    pass


def query(sql: str, params: tuple | list | dict = ()) -> list[dict]:
    """Execute raw SQL read query via SQLAlchemy session and return list of dicts."""
    if isinstance(params, (list, tuple)):
        # For compatibility with legacy '?' positional queries
        converted_sql = sql.replace("?", ":p")
        # Replace multiple :p with :p0, :p1, etc.
        parts = converted_sql.split(":p")
        new_sql = parts[0]
        param_dict = {}
        for i, val in enumerate(params):
            new_sql += f":p{i}" + parts[i + 1]
            param_dict[f"p{i}"] = val
        res = db.session.execute(text(new_sql), param_dict)
    else:
        res = db.session.execute(text(sql), params)
    return [dict(row._mapping) for row in res.fetchall()]


def query_one(sql: str, params: tuple | list | dict = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list | dict = ()) -> int:
    """Execute raw SQL modification query via SQLAlchemy session."""
    if isinstance(params, (list, tuple)):
        converted_sql = sql.replace("?", ":p")
        parts = converted_sql.split(":p")
        new_sql = parts[0]
        param_dict = {}
        for i, val in enumerate(params):
            new_sql += f":p{i}" + parts[i + 1]
            param_dict[f"p{i}"] = val
        res = db.session.execute(text(new_sql), param_dict)
    else:
        res = db.session.execute(text(sql), params)
    db.session.commit()
    return getattr(res, "lastrowid", 0) or getattr(res, "rowcount", 0)


def init_app(app) -> None:
    pass