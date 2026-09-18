"""Anomaly detection.

Purpose: narrow the search space *before* the LLM reasons about it.  Instead of
asking a model to eyeball 24 products, we score every entity against its own
history and flag the ones that genuinely broke pattern.

Two complementary signals:
  * robust z-score  -- how far the current month sits from that entity's own
    trailing median, scaled by MAD (resistant to the odd spiky month);
  * IsolationForest -- multivariate outlier score across the peer group, so an
    entity that is unusual in *combination* (big drop + big share) is caught.

The IsolationForest is skipped when the peer group is too small to be meaningful
(<8 entities), and that is reported honestly in `method`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.analytics.metrics import DIMENSIONS, _frame, _needed_joins, _where
from app.analytics.periods import Period

MIN_ENTITIES_FOR_FOREST = 8
Z_FLAG = 2.0


def _history(dimension: str, cur: Period, months: int, filters: dict) -> pd.DataFrame:
    spec = DIMENSIONS[dimension]
    where, fparams = _where(filters or {})
    joins = " ".join(_needed_joins(filters or {}, {spec["join"]}))
    start = (pd.Timestamp(cur.end) - pd.DateOffset(months=months)).replace(day=1).date()
    sql = f"""
        SELECT {spec['key']} AS key, {spec['label']} AS label, s.date AS date,
               s.revenue AS revenue, s.quantity AS quantity
        FROM sales s {joins}
        WHERE s.date BETWEEN :h_start AND :cur_end{where}
    """
    df = _frame(sql, {"h_start": start, "cur_end": cur.end} | fparams)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df.date.dt.to_period("M").astype(str)
    return df


def detect_anomalies(dimension: str, cur: Period, filters: dict | None = None,
                     months: int = 12) -> dict:
    """Flag entities whose current-period revenue breaks their own pattern."""
    if dimension not in DIMENSIONS:
        raise ValueError(f"unsupported dimension: {dimension}")
    df = _history(dimension, cur, months, filters or {})
    if df.empty:
        return {"dimension": dimension, "entities": [], "method": "no data"}

    cur_month = pd.Timestamp(cur.start).to_period("M").strftime("%Y-%m")
    pivot = df.pivot_table(index="key", columns="month", values="revenue", aggfunc="sum").fillna(0.0)
    labels = df.groupby("key").label.first()
    if cur_month not in pivot.columns:
        return {"dimension": dimension, "entities": [], "method": "current period not aligned to a month"}

    hist = pivot.drop(columns=[cur_month])
    current = pivot[cur_month]
    med = hist.median(axis=1)
    mad = (hist.sub(med, axis=0)).abs().median(axis=1) * 1.4826
    scale = mad.replace(0, np.nan).fillna(hist.std(axis=1)).replace(0, np.nan)
    z = ((current - med) / scale).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    prev_month = sorted(hist.columns)[-1] if len(hist.columns) else None
    previous = hist[prev_month] if prev_month else current * 0
    pct_change = ((current - previous) / previous.replace(0, np.nan) * 100).fillna(0.0)
    share = current / current.sum() * 100 if current.sum() else current * 0

    feats = pd.DataFrame({"z": z, "pct_change": pct_change, "share": share,
                          "delta": current - previous}).fillna(0.0)
    method = "robust z-score (MAD)"
    if_score = pd.Series(0.0, index=feats.index)
    if len(feats) >= MIN_ENTITIES_FOR_FOREST:
        X = ((feats - feats.mean()) / feats.std(ddof=0).replace(0, 1)).to_numpy()
        forest = IsolationForest(n_estimators=200, contamination=0.12, random_state=7).fit(X)
        raw = -forest.score_samples(X)          # higher = more anomalous
        if_score = pd.Series((raw - raw.min()) / (float(np.ptp(raw)) or 1), index=feats.index)
        method = "robust z-score (MAD) + IsolationForest"

    z_component = (z.abs() / 4.0).clip(0, 1)
    score = (0.6 * z_component + 0.4 * if_score).round(3)

    rows = []
    for key in feats.index:
        rows.append({
            "key": key, "label": str(labels.get(key, key)),
            "current_revenue": round(float(current[key]), 2),
            "previous_revenue": round(float(previous[key]), 2),
            "pct_change": round(float(pct_change[key]), 2),
            "expected_revenue_median": round(float(med[key]), 2),
            "z_score": round(float(z[key]), 2),
            "isolation_forest_score": round(float(if_score[key]), 3),
            "anomaly_score": float(score[key]),
            "is_anomaly": bool(abs(z[key]) >= Z_FLAG or if_score[key] >= 0.85),
            "direction": "below expectation" if z[key] < 0 else "above expectation",
        })
    rows.sort(key=lambda r: (-r["anomaly_score"], r["pct_change"]))
    return {
        "dimension": dimension, "period": cur.as_dict(), "filters": filters or {},
        "method": method, "history_months": int(len(hist.columns)),
        "flagged": [r for r in rows if r["is_anomaly"]],
        "entities": rows,
    }


def demand_vs_served(cur: Period, product_id: str, region_id: str | None = None) -> dict:
    """Compare true demand (sold + lost) against what inventory could serve.

    This is the cleanest possible evidence that a decline is a *supply* problem
    rather than a demand problem, and it needs no model at all.
    """
    params = {"cur_start": cur.start, "cur_end": cur.end, "product_id": product_id}
    clause = ""
    if region_id:
        clause = " AND region_id = :region_id"
        params["region_id"] = region_id
    df = _frame(f"""
        SELECT date AS date, units_sold AS units_sold, units_lost AS units_lost
        FROM inventory
        WHERE date BETWEEN :cur_start AND :cur_end AND product_id = :product_id{clause}
    """, params)
    if df.empty:
        return {}
    sold, lost = int(df.units_sold.sum()), int(df.units_lost.sum())
    demand = sold + lost
    return {
        "product_id": product_id, "region_id": region_id, "period": cur.as_dict(),
        "true_demand_units": demand, "served_units": sold, "unserved_units": lost,
        "fill_rate_pct": round(sold / demand * 100, 1) if demand else None,
        "interpretation": ("demand was present but could not be served (supply-side)"
                           if lost > 0.05 * max(demand, 1) else
                           "inventory served essentially all demand (demand-side)"),
    }
