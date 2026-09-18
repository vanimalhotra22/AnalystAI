"""Period resolution.

The agent never invents a date range.  A natural-language period expression is
resolved here, deterministically, against the *data's own* calendar (the latest
date present in `sales`), and every downstream metric carries the resolved
range so the report can state exactly what was compared.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from sqlalchemy import text

from app.db.session import ro_engine

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def as_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(),
                "label": self.label, "days": self.days}

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.label} ({self.start} .. {self.end})"


@lru_cache(maxsize=1)
def data_bounds() -> tuple[date, date]:
    with ro_engine().connect() as c:
        lo, hi = c.execute(text("SELECT MIN(date), MAX(date) FROM sales")).one()
    to_d = lambda v: v if isinstance(v, date) else date.fromisoformat(str(v)[:10])
    return to_d(lo), to_d(hi)


def month_period(year: int, month: int) -> Period:
    last = calendar.monthrange(year, month)[1]
    return Period(date(year, month, 1), date(year, month, last),
                  f"{calendar.month_name[month]} {year}")


def _shift_month(p: Period, months: int) -> Period:
    y, m = p.start.year, p.start.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return month_period(y, m)


def resolve_period(expr: str | None = None, anchor: date | None = None) -> Period:
    """Turn 'this month', 'July 2026', '2026-07', 'last 30 days', 'Q2 2026' ...
    into a concrete range.  Unrecognised input falls back to the latest complete
    month in the dataset, which is what a manager means by 'this month'."""
    _, hi = data_bounds()
    anchor = anchor or hi
    e = (expr or "").strip().lower()

    # The dataset ends with a complete month, and the user is standing just after
    # it, so "this month", "last month" and "the latest month" all mean that same
    # month.  Anything earlier has to be named explicitly (e.g. "June 2026").
    if not e or e in {"this month", "current month", "the last month", "mtd", "month to date",
                      "last month", "previous month", "prior month", "latest month"}:
        return month_period(anchor.year, anchor.month)

    m = re.fullmatch(r"(\d{4})-(\d{1,2})", e)
    if m:
        return month_period(int(m.group(1)), int(m.group(2)))

    m = re.fullmatch(r"([a-z]+)\s*(\d{4})?", e)
    if m and m.group(1) in MONTHS:
        return month_period(int(m.group(2) or anchor.year), MONTHS[m.group(1)])

    m = re.fullmatch(r"q([1-4])\s*(\d{4})?", e)
    if m:
        q, y = int(m.group(1)), int(m.group(2) or anchor.year)
        start = date(y, 3 * q - 2, 1)
        end_m = 3 * q
        return Period(start, date(y, end_m, calendar.monthrange(y, end_m)[1]), f"Q{q} {y}")

    m = re.fullmatch(r"last\s+(\d+)\s+days?", e)
    if m:
        n = int(m.group(1))
        return Period(anchor - timedelta(days=n - 1), anchor, f"last {n} days")

    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s*(?:to|\.\.|-)\s*(\d{4}-\d{2}-\d{2})", e)
    if m:
        a, b = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
        return Period(a, b, f"{a} to {b}")

    if e in {"ytd", "year to date"}:
        return Period(date(anchor.year, 1, 1), anchor, f"YTD {anchor.year}")

    return month_period(anchor.year, anchor.month)


def resolve_comparison(period: Period, expr: str | None = None) -> Period:
    """Default comparison is the immediately preceding period of equal shape."""
    e = (expr or "").strip().lower()
    if e in {"", "previous period", "previous month", "prior period", "last month", "mom"}:
        if period.start.day == 1 and period.end.day == calendar.monthrange(period.end.year, period.end.month)[1]:
            return _shift_month(period, -1)
        length = period.days
        end = period.start - timedelta(days=1)
        return Period(end - timedelta(days=length - 1), end, "previous period")
    if e in {"same month last year", "last year", "yoy", "same period last year"}:
        return month_period(period.start.year - 1, period.start.month)
    return resolve_period(expr)


def describe_calendar() -> dict:
    lo, hi = data_bounds()
    cur = month_period(hi.year, hi.month)
    return {
        "data_start": lo.isoformat(), "data_end": hi.isoformat(),
        "latest_complete_month": cur.label,
        "default_current_period": cur.as_dict(),
        "default_comparison_period": resolve_comparison(cur).as_dict(),
    }
