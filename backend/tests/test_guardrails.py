"""The SQL guard is a security control, so it gets real tests."""
from __future__ import annotations

import pytest

from app.agents.sql_tool import SQLGuardError, run_sql, validate

REFUSED = [
    "DROP TABLE sales",
    "DELETE FROM sales WHERE 1=1",
    "UPDATE sales SET revenue = 0",
    "INSERT INTO sales (revenue) VALUES (1)",
    "ALTER TABLE sales ADD COLUMN x INT",
    "TRUNCATE TABLE sales",
    "SELECT * FROM sales; DELETE FROM sales",
    "SELECT * FROM sqlite_master",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM pg_catalog.pg_user",
    "SELECT revenue FROM sales -- and then something else",
    "SELECT revenue FROM sales /* sneaky */",
    "PRAGMA table_info(sales)",
    "ATTACH DATABASE 'other.db' AS o",
    "",
]

ALLOWED = [
    "SELECT SUM(revenue) FROM sales",
    "SELECT region_id, SUM(revenue) FROM sales GROUP BY region_id",
    """WITH monthly AS (SELECT date, revenue FROM sales) SELECT SUM(revenue) FROM monthly""",
    "SELECT s.revenue FROM sales s JOIN products p ON p.product_id = s.product_id",
]


@pytest.mark.parametrize("sql", REFUSED)
def test_dangerous_sql_is_refused(sql):
    with pytest.raises(SQLGuardError):
        validate(sql)


@pytest.mark.parametrize("sql", ALLOWED)
def test_read_only_sql_is_allowed(sql):
    assert validate(sql).lower().startswith(("select", "with"))


def test_row_limit_is_injected_and_enforced():
    assert "LIMIT" in validate("SELECT revenue FROM sales")
    res = run_sql("SELECT revenue FROM sales", row_limit=10)
    assert res.row_count == 10
    assert res.truncated is True


def test_explicit_limit_is_respected():
    assert validate("SELECT revenue FROM sales LIMIT 3").endswith("LIMIT 3")


def test_read_only_connection_rejects_writes():
    """Second gate: even a write that slipped past the validator must fail."""
    from sqlalchemy import text
    from app.db.session import ro_engine
    with pytest.raises(Exception):
        with ro_engine().connect() as c:
            c.execute(text("DELETE FROM sales"))
            c.commit()
