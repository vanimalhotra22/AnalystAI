"""Deterministic business metrics.

Every number the system reports is produced here, in Python/SQL -- never by the
language model.  The LLM decides *which* of these to call and how to narrate the
result; it is not allowed to do arithmetic on business data.

All SQL is parameterised and portable (no dialect-specific date functions), so
the same code runs on SQLite and PostgreSQL.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text

from app.analytics.periods import Period
from app.db.session import ro_engine

# Only these filters may reach the WHERE clause, and always as bound parameters.
FILTERS = {
    "product_id": "s.product_id = :f_product_id",
    "region_id": "s.region_id = :f_region_id",
    "channel_id": "s.channel_id = :f_channel_id",
    "category": "p.category = :f_category",
    "subcategory": "p.subcategory = :f_subcategory",
    "segment": "c.segment = :f_segment",
    "supplier_id": "p.supplier_id = :f_supplier_id",
}

DIMENSIONS: dict[str, dict[str, str]] = {
    "region":   {"key": "s.region_id", "label": "r.region_name", "join": "region"},
    "product":  {"key": "s.product_id", "label": "p.product_name", "join": "product"},
    "category": {"key": "p.category", "label": "p.category", "join": "product"},
    "channel":  {"key": "s.channel_id", "label": "ch.channel_name", "join": "channel"},
    "segment":  {"key": "c.segment", "label": "c.segment", "join": "customer"},
    "age_group": {"key": "c.age_group", "label": "c.age_group", "join": "customer"},
    "supplier": {"key": "p.supplier_id", "label": "sup.supplier_name", "join": "supplier"},
}

_JOINS = {
    "product":  "JOIN products p ON p.product_id = s.product_id",
    "region":   "JOIN regions r ON r.region_id = s.region_id",
    "channel":  "JOIN channels ch ON ch.channel_id = s.channel_id",
    "customer": "JOIN customers c ON c.customer_id = s.customer_id",
    "supplier": "JOIN products p ON p.product_id = s.product_id "
                "JOIN suppliers sup ON sup.supplier_id = p.supplier_id",
}


# ---------------------------------------------------------------- formatting
def fmt_inr(value: float | None) -> str:
    """Indian numbering for display: crore / lakh / thousand."""
    if value is None:
        return "n/a"
    v, sign = abs(float(value)), "-" if value < 0 else ""
    if v >= 1e7:
        return f"{sign}₹{v / 1e7:,.2f} Cr"
    if v >= 1e5:
        return f"{sign}₹{v / 1e5:,.2f} L"
    if v >= 1e3:
        return f"{sign}₹{v / 1e3:,.1f} K"
    return f"{sign}₹{v:,.0f}"


def pct(new: float, old: float) -> float | None:
    if not old:
        return None
    return round((new - old) / old * 100, 2)


# ------------------------------------------------------------------ plumbing
def _needed_joins(filters: dict, extra: set[str]) -> list[str]:
    need = set(extra)
    if "category" in filters or "subcategory" in filters or "supplier_id" in filters:
        need.add("product")
    if "segment" in filters:
        need.add("customer")
    if "supplier" in need:
        need.discard("product")  # the supplier join already brings products in
    return [_JOINS[j] for j in ("supplier", "product", "region", "channel", "customer") if j in need]


def _where(filters: dict) -> tuple[str, dict]:
    clauses, params = [], {}
    for k, v in (filters or {}).items():
        if v in (None, "", "all"):
            continue
        if k not in FILTERS:
            raise ValueError(f"unsupported filter: {k}")
        clauses.append(FILTERS[k])
        params[f"f_{k}"] = v
    return ("".join(f" AND {c}" for c in clauses), params)


def _frame(sql: str, params: dict) -> pd.DataFrame:
    with ro_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def _period_params(cur: Period, prev: Period | None) -> dict:
    p = {"cur_start": cur.start, "cur_end": cur.end}
    if prev:
        p |= {"prev_start": prev.start, "prev_end": prev.end}
    return p


# -------------------------------------------------------------------- totals
def revenue_summary(cur: Period, prev: Period | None = None, filters: dict | None = None) -> dict:
    filters = filters or {}
    where, fparams = _where(filters)
    joins = " ".join(_needed_joins(filters, set()))
    span = "s.date BETWEEN :prev_start AND :cur_end" if prev else "s.date BETWEEN :cur_start AND :cur_end"
    sql = f"""
        SELECT s.date AS date, s.revenue AS revenue, s.profit AS profit,
               s.quantity AS quantity, s.sale_id AS sale_id
        FROM sales s {joins}
        WHERE {span}{where}
    """
    df = _frame(sql, _period_params(cur, prev) | fparams)
    df["date"] = pd.to_datetime(df["date"])

    def agg(p: Period) -> dict:
        d = df[(df.date >= pd.Timestamp(p.start)) & (df.date <= pd.Timestamp(p.end))]
        rev = float(d.revenue.sum())
        return {
            "period": p.as_dict(), "revenue": round(rev, 2), "profit": round(float(d.profit.sum()), 2),
            "units": int(d.quantity.sum()), "orders": int(len(d)),
            "avg_order_value": round(rev / len(d), 2) if len(d) else 0.0,
            "revenue_per_day": round(rev / p.days, 2),
        }

    out: dict[str, Any] = {"current": agg(cur), "filters": filters}
    if prev:
        c, p = out["current"], agg(prev)
        out["previous"] = p
        out["change"] = {
            "revenue_delta": round(c["revenue"] - p["revenue"], 2),
            "revenue_pct": pct(c["revenue"], p["revenue"]),
            # Months differ in length; the per-day rate is the like-for-like view.
            "revenue_per_day_pct": pct(c["revenue_per_day"], p["revenue_per_day"]),
            "units_pct": pct(c["units"], p["units"]),
            "orders_pct": pct(c["orders"], p["orders"]),
            "aov_pct": pct(c["avg_order_value"], p["avg_order_value"]),
            "profit_pct": pct(c["profit"], p["profit"]),
            "days_current": cur.days, "days_previous": prev.days,
        }
    return out


# ---------------------------------------------------------------- breakdowns
def breakdown(dimension: str, cur: Period, prev: Period, filters: dict | None = None,
              top_n: int = 12) -> dict:
    """Revenue by dimension for both periods, with each member's contribution to
    the overall change (the classic 'who moved the number' table)."""
    if dimension not in DIMENSIONS:
        raise ValueError(f"unsupported dimension: {dimension} (use {sorted(DIMENSIONS)})")
    spec = DIMENSIONS[dimension]
    filters = filters or {}
    where, fparams = _where(filters)
    joins = " ".join(_needed_joins(filters, {spec["join"]}))
    sql = f"""
        SELECT {spec['key']} AS key, {spec['label']} AS label,
               SUM(CASE WHEN s.date BETWEEN :cur_start AND :cur_end THEN s.revenue ELSE 0 END) AS current_revenue,
               SUM(CASE WHEN s.date BETWEEN :prev_start AND :prev_end THEN s.revenue ELSE 0 END) AS previous_revenue,
               SUM(CASE WHEN s.date BETWEEN :cur_start AND :cur_end THEN s.quantity ELSE 0 END) AS current_units,
               SUM(CASE WHEN s.date BETWEEN :prev_start AND :prev_end THEN s.quantity ELSE 0 END) AS previous_units
        FROM sales s {joins}
        WHERE s.date BETWEEN :prev_start AND :cur_end{where}
        GROUP BY {spec['key']}, {spec['label']}
    """
    df = _frame(sql, _period_params(cur, prev) | fparams)
    if df.empty:
        return {"dimension": dimension, "rows": [], "total_delta": 0.0}

    df["delta"] = df.current_revenue - df.previous_revenue
    df["pct_change"] = df.apply(lambda r: pct(r.current_revenue, r.previous_revenue), axis=1)
    total_delta = float(df.delta.sum())
    decline = float(df.loc[df.delta < 0, "delta"].sum())
    df["contribution_pct"] = df.delta / total_delta * 100 if total_delta else None
    df["share_of_decline_pct"] = df.delta.apply(
        lambda d: round(d / decline * 100, 1) if decline and d < 0 else 0.0)
    df["current_share_pct"] = df.current_revenue / df.current_revenue.sum() * 100

    df = df.sort_values("delta")
    rows = [{
        "key": r.key, "label": r.label,
        "current_revenue": round(float(r.current_revenue), 2),
        "previous_revenue": round(float(r.previous_revenue), 2),
        "delta": round(float(r.delta), 2),
        "pct_change": r.pct_change,
        "contribution_pct": round(float(r.contribution_pct), 1) if pd.notna(r.contribution_pct) else None,
        "share_of_decline_pct": float(r.share_of_decline_pct),
        "current_share_pct": round(float(r.current_share_pct), 1),
        "current_units": int(r.current_units), "previous_units": int(r.previous_units),
    } for r in df.itertuples()]

    worst = rows[0] if rows else None
    return {
        "dimension": dimension, "current_period": cur.as_dict(), "previous_period": prev.as_dict(),
        "filters": filters, "total_delta": round(total_delta, 2),
        "rows": rows[:top_n] + ([] if len(rows) <= top_n else rows[-2:]),
        "largest_decline": worst,
    }


def trend(cur: Period, months: int = 13, filters: dict | None = None, grain: str = "month") -> dict:
    """Revenue time series ending with `cur`.  Grouping happens in pandas so the
    SQL stays dialect-neutral."""
    filters = filters or {}
    where, fparams = _where(filters)
    joins = " ".join(_needed_joins(filters, set()))
    start = (pd.Timestamp(cur.end) - pd.DateOffset(months=months - 1)).replace(day=1).date()
    sql = f"""
        SELECT s.date AS date, s.revenue AS revenue, s.quantity AS quantity
        FROM sales s {joins}
        WHERE s.date BETWEEN :t_start AND :cur_end{where}
    """
    df = _frame(sql, {"t_start": start, "cur_end": cur.end} | fparams)
    if df.empty:
        return {"grain": grain, "points": []}
    df["date"] = pd.to_datetime(df["date"])
    key = df.date.dt.to_period("M").astype(str) if grain == "month" else df.date.dt.date.astype(str)
    g = df.groupby(key).agg(revenue=("revenue", "sum"), units=("quantity", "sum")).reset_index()
    g.columns = ["period", "revenue", "units"]
    if grain == "month":
        days = df.groupby(key)["date"].nunique().values
        g["revenue_per_day"] = (g.revenue / days).round(2)
    g["mom_pct"] = g.revenue.pct_change().mul(100).round(2)
    # NaN is not valid JSON, and the first month has no month-on-month value.
    records = [{k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in row.items()}
               for row in g.round(2).to_dict("records")]
    return {"grain": grain, "filters": filters, "points": records}


# ----------------------------------------------------------------- inventory
def inventory_health(cur: Period, product_id: str | None = None, region_id: str | None = None,
                     prev: Period | None = None) -> dict:
    params = {"cur_start": cur.start, "cur_end": cur.end}
    clauses = ""
    if product_id:
        clauses += " AND i.product_id = :product_id"
        params["product_id"] = product_id
    if region_id:
        clauses += " AND i.region_id = :region_id"
        params["region_id"] = region_id
    sql = f"""
        SELECT i.date AS date, i.product_id AS product_id, i.region_id AS region_id,
               i.warehouse_id AS warehouse_id, i.opening_stock AS opening_stock,
               i.units_received AS units_received, i.units_sold AS units_sold,
               i.units_lost AS units_lost, i.closing_stock AS closing_stock,
               i.stockout AS stockout, p.unit_price AS unit_price, p.product_name AS product_name
        FROM inventory i JOIN products p ON p.product_id = i.product_id
        WHERE i.date BETWEEN :cur_start AND :cur_end{clauses}
    """
    df = _frame(sql, params)
    if df.empty:
        return {"period": cur.as_dict(), "stockout_days": 0, "rows": []}
    df["date"] = pd.to_datetime(df["date"])
    df["stockout"] = df.stockout.astype(bool)

    by_pr = df.groupby(["product_id", "product_name", "region_id"]).agg(
        stockout_days=("stockout", "sum"), units_lost=("units_lost", "sum"),
        units_sold=("units_sold", "sum"), min_closing=("closing_stock", "min"),
        unit_price=("unit_price", "max")).reset_index()
    by_pr["lost_revenue_estimate"] = (by_pr.units_lost * by_pr.unit_price * 0.92).round(2)
    by_pr = by_pr.sort_values("lost_revenue_estimate", ascending=False)

    daily = (df.groupby("date").agg(closing_stock=("closing_stock", "sum"),
                                    units_sold=("units_sold", "sum"),
                                    units_lost=("units_lost", "sum"),
                                    stockout=("stockout", "max")).reset_index())
    daily["date"] = daily.date.dt.date.astype(str)

    # longest consecutive run of stockout days (only meaningful for one entity)
    longest, run, run_start, best_span = 0, 0, None, (None, None)
    for _, row in daily.iterrows():
        if row.stockout:
            run += 1
            run_start = run_start or row.date
            if run > longest:
                longest, best_span = run, (run_start, row.date)
        else:
            run, run_start = 0, None

    return {
        "period": cur.as_dict(), "product_id": product_id, "region_id": region_id,
        "stockout_days": int(df.groupby("date").stockout.max().sum()),
        "longest_stockout_streak_days": int(longest),
        "stockout_window": {"start": best_span[0], "end": best_span[1]},
        "units_lost": int(df.units_lost.sum()),
        "lost_revenue_estimate": round(float((df.units_lost * df.unit_price * 0.92).sum()), 2),
        "by_product_region": by_pr.head(15).round(2).to_dict("records"),
        "daily": daily.to_dict("records"),
    }


def supplier_performance(cur: Period, supplier_id: str | None = None,
                         product_id: str | None = None, lookback_days: int = 120) -> dict:
    params = {"start": cur.start - pd.Timedelta(days=lookback_days).to_pytimedelta(), "end": cur.end}
    clauses = ""
    if supplier_id:
        clauses += " AND po.supplier_id = :supplier_id"
        params["supplier_id"] = supplier_id
    if product_id:
        clauses += " AND po.product_id = :product_id"
        params["product_id"] = product_id
    sql = f"""
        SELECT po.po_id AS po_id, po.order_date AS order_date, po.product_id AS product_id,
               po.supplier_id AS supplier_id, su.supplier_name AS supplier_name,
               su.standard_lead_time_days AS standard_lead_time_days,
               su.reliability_score AS reliability_score,
               po.region_id AS region_id, po.warehouse_id AS warehouse_id, po.quantity AS quantity,
               po.promised_date AS promised_date, po.received_date AS received_date,
               po.delay_days AS delay_days
        FROM purchase_orders po JOIN suppliers su ON su.supplier_id = po.supplier_id
        WHERE po.received_date BETWEEN :start AND :end{clauses}
    """
    df = _frame(sql, params)
    if df.empty:
        return {"purchase_orders": 0, "rows": []}
    df["received_date"] = pd.to_datetime(df["received_date"])
    in_period = df[(df.received_date >= pd.Timestamp(cur.start)) & (df.received_date <= pd.Timestamp(cur.end))]
    baseline = df[df.received_date < pd.Timestamp(cur.start)]
    by_sup = df.groupby(["supplier_id", "supplier_name"]).agg(
        pos=("po_id", "count"), avg_delay_days=("delay_days", "mean"),
        max_delay_days=("delay_days", "max"),
        late_pos=("delay_days", lambda s: int((s > 2).sum()))).reset_index().round(2)
    worst = df.sort_values("delay_days", ascending=False).head(6)
    return {
        "period": cur.as_dict(), "purchase_orders": int(len(df)),
        "avg_delay_days_in_period": round(float(in_period.delay_days.mean()), 2) if len(in_period) else None,
        "avg_delay_days_baseline": round(float(baseline.delay_days.mean()), 2) if len(baseline) else None,
        "by_supplier": by_sup.to_dict("records"),
        "worst_purchase_orders": worst.assign(
            order_date=lambda d: d.order_date.astype(str),
            promised_date=lambda d: d.promised_date.astype(str),
            received_date=lambda d: d.received_date.dt.date.astype(str),
        )[["po_id", "product_id", "supplier_name", "region_id", "warehouse_id", "quantity",
           "order_date", "promised_date", "received_date", "delay_days"]].to_dict("records"),
    }


# ----------------------------------------------------------------- marketing
def marketing_performance(cur: Period, prev: Period, filters: dict | None = None) -> dict:
    filters = filters or {}
    clauses, params = "", _period_params(cur, prev)
    if filters.get("region_id"):
        clauses += " AND m.region_id = :region_id"
        params["region_id"] = filters["region_id"]
    if filters.get("product_id"):
        clauses += " AND m.product_id = :product_id"
        params["product_id"] = filters["product_id"]
    if filters.get("category"):
        clauses += " AND p.category = :category"
        params["category"] = filters["category"]
    sql = f"""
        SELECT m.date AS date, m.region_id AS region_id, m.product_id AS product_id,
               p.category AS category, m.channel AS channel, m.spend AS spend,
               m.impressions AS impressions, m.clicks AS clicks, m.conversions AS conversions
        FROM marketing m JOIN products p ON p.product_id = m.product_id
        WHERE m.date BETWEEN :prev_start AND :cur_end{clauses}
    """
    df = _frame(sql, params)
    if df.empty:
        return {"spend_current": 0, "spend_previous": 0}
    df["date"] = pd.to_datetime(df["date"])
    c = df[(df.date >= pd.Timestamp(cur.start)) & (df.date <= pd.Timestamp(cur.end))]
    p = df[(df.date >= pd.Timestamp(prev.start)) & (df.date <= pd.Timestamp(prev.end))]
    by_region = df.assign(period=lambda d: d.date.apply(
        lambda x: "current" if x >= pd.Timestamp(cur.start) else "previous")) \
        .pivot_table(index="region_id", columns="period", values="spend", aggfunc="sum").reset_index()
    if "current" in by_region and "previous" in by_region:
        by_region["pct_change"] = ((by_region["current"] - by_region["previous"]) /
                                   by_region["previous"] * 100).round(2)
    return {
        "current_period": cur.as_dict(), "previous_period": prev.as_dict(), "filters": filters,
        "spend_current": round(float(c.spend.sum()), 2),
        "spend_previous": round(float(p.spend.sum()), 2),
        "spend_pct_change": pct(float(c.spend.sum()), float(p.spend.sum())),
        "clicks_pct_change": pct(float(c.clicks.sum()), float(p.clicks.sum())),
        "conversions_pct_change": pct(float(c.conversions.sum()), float(p.conversions.sum())),
        "by_region": by_region.round(2).to_dict("records"),
    }


# ------------------------------------------------------- pricing & customers
def pricing_check(cur: Period, prev: Period, filters: dict | None = None) -> dict:
    """Rules out (or in) price/discount as a driver."""
    filters = filters or {}
    where, fparams = _where(filters)
    joins = " ".join(_needed_joins(filters, set()))
    sql = f"""
        SELECT s.date AS date, s.unit_price AS unit_price, s.discount_pct AS discount_pct,
               s.revenue AS revenue, s.quantity AS quantity
        FROM sales s {joins}
        WHERE s.date BETWEEN :prev_start AND :cur_end{where}
    """
    df = _frame(sql, _period_params(cur, prev) | fparams)
    if df.empty:
        return {}
    df["date"] = pd.to_datetime(df["date"])

    def agg(p: Period) -> dict:
        d = df[(df.date >= pd.Timestamp(p.start)) & (df.date <= pd.Timestamp(p.end))]
        return {
            "avg_list_price": round(float(d.unit_price.mean()), 2),
            "avg_discount_pct": round(float(d.discount_pct.mean()) * 100, 2),
            "realised_price_per_unit": round(float(d.revenue.sum() / d.quantity.sum()), 2) if d.quantity.sum() else None,
        }

    c, p = agg(cur), agg(prev)
    return {"current": c, "previous": p, "filters": filters,
            "discount_pct_point_change": round(c["avg_discount_pct"] - p["avg_discount_pct"], 2),
            "realised_price_pct_change": pct(c["realised_price_per_unit"], p["realised_price_per_unit"])}


def customer_metrics(cur: Period, prev: Period, filters: dict | None = None) -> dict:
    filters = filters or {}
    where, fparams = _where(filters)
    joins = " ".join(_needed_joins(filters, {"customer"}))
    sql = f"""
        SELECT s.date AS date, s.customer_id AS customer_id, s.revenue AS revenue,
               c.segment AS segment
        FROM sales s {joins}
        WHERE s.date BETWEEN :prev_start AND :cur_end{where}
    """
    df = _frame(sql, _period_params(cur, prev) | fparams)
    if df.empty:
        return {}
    df["date"] = pd.to_datetime(df["date"])
    c = df[(df.date >= pd.Timestamp(cur.start)) & (df.date <= pd.Timestamp(cur.end))]
    p = df[(df.date >= pd.Timestamp(prev.start)) & (df.date <= pd.Timestamp(prev.end))]
    prev_ids = set(p.customer_id)
    seg = (c.groupby("segment").revenue.sum() / c.revenue.sum() * 100).round(1).to_dict()
    seg_prev = (p.groupby("segment").revenue.sum() / p.revenue.sum() * 100).round(1).to_dict()
    return {
        "active_customers_current": int(c.customer_id.nunique()),
        "active_customers_previous": int(p.customer_id.nunique()),
        "active_customers_pct_change": pct(c.customer_id.nunique(), p.customer_id.nunique()),
        "returning_customers_current": int(len(set(c.customer_id) & prev_ids)),
        "revenue_per_customer_current": round(float(c.revenue.sum() / max(c.customer_id.nunique(), 1)), 2),
        "revenue_per_customer_previous": round(float(p.revenue.sum() / max(p.customer_id.nunique(), 1)), 2),
        "segment_revenue_mix_current_pct": seg,
        "segment_revenue_mix_previous_pct": seg_prev,
    }
