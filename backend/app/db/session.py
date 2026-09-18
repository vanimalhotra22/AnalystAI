"""Engine factory.  Two engines: a read/write one used only by the seeder, and a
read-only one that is the *only* connection the agent's SQL tool can touch."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from app.config import settings

# Python 3.12 deprecated sqlite3's implicit date adapters; register the
# documented replacements so dates bind as ISO strings on every version.
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_adapter(datetime, lambda d: d.isoformat(sep=" "))

_rw: Engine | None = None
_ro: Engine | None = None


def _tune(engine: Engine) -> Engine:
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _pragma(dbapi_conn, _rec):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()
    return engine


def rw_engine() -> Engine:
    global _rw
    if _rw is None:
        url = settings.database_url
        if url.startswith("sqlite:///"):
            Path(url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
        _rw = _tune(create_engine(url, future=True))
    return _rw


def ro_engine() -> Engine:
    """Read-only engine.

    SQLite: opened with mode=ro so a stray write raises at the driver level.
    Postgres: point READONLY_DATABASE_URL at a role with SELECT-only grants.
    This is defence in depth -- the SQL validator (app/agents/sql_tool.py) is the
    first gate, the connection privileges are the second.
    """
    global _ro
    if _ro is None:
        _ro = _tune(create_engine(settings.ro_url, future=True))
    return _ro
