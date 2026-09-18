"""Metrics are the part the business acts on, so they are checked against
independently written SQL rather than against themselves."""
from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.analytics import metrics as M
from app.analytics.anomaly import demand_vs_served, detect_anomalies
from app.analytics.impact import quantify_stockout_impact
from app.analytics.periods import Period, resolve_comparison, resolve_period
from app.db.session import ro_engine

CUR = resolve_period("this month")
PREV = resolve_comparison(CUR)


def _sql_scalar(sql: str, **params):
    with ro_engine().connect() as c:
        return c.execute(text(sql), params).scalar()


# ------------------------------------------------------------------ periods
def test_period_resolution():
    assert resolve_period("2026-07") == Period(date(2026, 7, 1), date(2026, 7, 31), "July 2026")
    assert resolve_period("June 2026").start == date(2026, 6, 1)
    assert resolve_period("Q2 2026").days == 91
    assert resolve_comparison(resolve_period("2026-07")).label == "June 2026"
    assert resolve_comparison(resolve_period("2026-07"), "same month last year").label == "July 2025"


def test_period_length_is_carried_not_assumed():
    assert CUR.days == 31 and PREV.days == 30


# ------------------------------------------------------------------ metrics
def test_revenue_summary_matches_independent_sql():
    res = M.revenue_summary(CUR, PREV)
    expected = _sql_scalar("SELECT SUM(revenue) FROM sales WHERE date BETWEEN :a AND :b",
                           a=CUR.start, b=CUR.end)
    assert round(res["current"]["revenue"], 2) == round(float(expected), 2)


def test_per_day_rate_differs_from_total_when_months_differ():
    ch = M.revenue_summary(CUR, PREV)["change"]
    assert ch["revenue_pct"] != ch["revenue_per_day_pct"]


def test_breakdown_deltas_sum_to_the_total_change():
    b = M.breakdown("region", CUR, PREV)
    total = M.revenue_summary(CUR, PREV)["change"]["revenue_delta"]
    assert abs(sum(r["delta"] for r in b["rows"]) - total) < 1.0


def test_breakdown_rejects_unknown_dimension():
    try:
        M.breakdown("colour", CUR, PREV)
    except ValueError as e:
        assert "unsupported dimension" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_filters_are_allow_listed():
    try:
        M.revenue_summary(CUR, PREV, {"; DROP TABLE sales": "x"})
    except ValueError as e:
        assert "unsupported filter" in str(e)
    else:
        raise AssertionError("expected ValueError")


# ---------------------------------------------------------------- inventory
def test_fill_rate_matches_the_ledger():
    res = demand_vs_served(CUR, "P103", "NORTH")
    sold = _sql_scalar("SELECT SUM(units_sold) FROM inventory WHERE product_id='P103' "
                       "AND region_id='NORTH' AND date BETWEEN :a AND :b", a=CUR.start, b=CUR.end)
    lost = _sql_scalar("SELECT SUM(units_lost) FROM inventory WHERE product_id='P103' "
                       "AND region_id='NORTH' AND date BETWEEN :a AND :b", a=CUR.start, b=CUR.end)
    assert res["served_units"] == sold
    assert res["unserved_units"] == lost
    assert res["true_demand_units"] == sold + lost


def test_impact_is_unserved_units_times_realised_price():
    imp = quantify_stockout_impact(CUR, "P103", "NORTH")
    assert abs(imp["lost_revenue"] - imp["unserved_units"] * imp["realised_price_per_unit"]) < 1.0
    assert "unserved units" in imp["method"]


# ------------------------------------------------------------------ anomaly
def test_anomaly_scan_flags_the_disrupted_line():
    res = detect_anomalies("product", CUR)
    flagged = {r["key"] for r in res["flagged"]}
    assert "P103" in flagged
    assert "IsolationForest" in res["method"]


def test_anomaly_scores_are_bounded():
    for row in detect_anomalies("product", CUR)["entities"]:
        assert 0.0 <= row["anomaly_score"] <= 1.0


# --------------------------------------------------------------- formatting
def test_currency_formatting():
    assert M.fmt_inr(14_200_000) == "₹1.42 Cr"
    assert M.fmt_inr(-1_840_000) == "-₹18.40 L"
    assert M.fmt_inr(None) == "n/a"
