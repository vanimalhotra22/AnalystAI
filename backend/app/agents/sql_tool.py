"""Guarded SQL execution.

The agent is never handed a database password and told to be careful.  Any SQL
that reaches the engine passes three gates:

  1. STATIC VALIDATION  single statement, must be SELECT/WITH, no DDL/DML verbs,
     no comment smuggling, no multi-statement piggybacking.
  2. SCHEMA ALLOW-LIST  every table referenced must be one of the nine analytics
     tables; anything else (sqlite_master, pg_catalog, information_schema...) is
     refused.
  3. LEAST PRIVILEGE    execution happens on a read-only connection (SQLite
     mode=ro / a SELECT-only Postgres role), so a bug in gates 1-2 still cannot
     mutate data.

A row cap is applied so a runaway query cannot exhaust memory or the context
window.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from sqlalchemy import text

from app.config import settings
from app.db.models import ALL_TABLES
from app.db.session import ro_engine

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|grant|revoke|"
    r"attach|detach|pragma|vacuum|copy|merge|call|execute|exec|reindex|analyze)\b",
    re.IGNORECASE)
COMMENT = re.compile(r"(--|/\*|\*/)")
TABLE_REF = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
LIMIT_RE = re.compile(r"\blimit\s+\d+\s*$", re.IGNORECASE)


class SQLGuardError(ValueError):
    """Raised when a generated query fails validation."""


@dataclass
class SQLResult:
    sql: str
    columns: list[str]
    rows: list[dict]
    row_count: int
    truncated: bool
    elapsed_ms: int


def validate(sql: str, row_limit: int | None = None) -> str:
    """Return an executable, capped statement, or raise SQLGuardError."""
    row_limit = row_limit or settings.sql_row_limit
    q = (sql or "").strip().rstrip(";").strip()
    if not q:
        raise SQLGuardError("empty query")
    if ";" in q:
        raise SQLGuardError("multiple statements are not allowed")
    if COMMENT.search(q):
        raise SQLGuardError("SQL comments are not allowed")
    if not re.match(r"^(select|with)\b", q, re.IGNORECASE):
        raise SQLGuardError("only SELECT / WITH queries are allowed")
    if FORBIDDEN.search(q):
        raise SQLGuardError("query contains a forbidden keyword (read-only access only)")

    referenced = {t.lower() for t in TABLE_REF.findall(q)}
    cte_names = {c.lower() for c in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", q, re.IGNORECASE)}
    unknown = referenced - set(ALL_TABLES) - cte_names
    if unknown:
        raise SQLGuardError(f"query references tables outside the analytics schema: {sorted(unknown)}")

    if not LIMIT_RE.search(q):
        # Fetch one row beyond the cap so truncation can be detected and reported
        # rather than silently changing the answer.
        q = f"{q} LIMIT {row_limit + 1}"
    return q


def run_sql(sql: str, params: dict | None = None, row_limit: int | None = None) -> SQLResult:
    """Validate, then execute on the read-only connection."""
    row_limit = row_limit or settings.sql_row_limit
    safe = validate(sql, row_limit)
    started = time.perf_counter()
    with ro_engine().connect() as conn:
        cur = conn.execute(text(safe), params or {})
        cols = list(cur.keys())
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    truncated = len(rows) > row_limit
    rows = rows[:row_limit]
    return SQLResult(sql=safe, columns=cols, rows=_jsonable(rows), row_count=len(rows),
                     truncated=truncated, elapsed_ms=int((time.perf_counter() - started) * 1000))


def _jsonable(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()})
    return out


SCHEMA_CARD = """\
Tables (read-only):
  sales(sale_id, date, product_id, customer_id, region_id, channel_id, quantity,
        unit_price, discount_pct, revenue, cost, profit)
  products(product_id, product_name, category, subcategory, unit_price, unit_cost,
        supplier_id, launch_date)
  regions(region_id, region_name, country, warehouse_id)
  customers(customer_id, segment, region_id, age_group, acquisition_channel, signup_date)
  channels(channel_id, channel_name)
  inventory(inventory_id, date, product_id, warehouse_id, region_id, opening_stock,
        units_received, units_sold, units_lost, closing_stock, stockout)
  marketing(campaign_id, date, product_id, region_id, channel, spend, impressions,
        clicks, conversions)
  suppliers(supplier_id, supplier_name, country, standard_lead_time_days, reliability_score)
  purchase_orders(po_id, order_date, product_id, supplier_id, warehouse_id, region_id,
        quantity, promised_date, received_date, delay_days)
Notes: region_id in {NORTH, SOUTH, EAST, WEST, CENTRAL}; marketing.date is the first
day of the campaign month; inventory.units_lost is demand that stock could not serve.
"""
