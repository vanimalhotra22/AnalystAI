"""Business impact quantification and what-if simulation.

Everything here is arithmetic or Monte-Carlo on real rows from the database.
The LLM is handed the result; it never estimates an impact figure itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics.metrics import _frame, fmt_inr
from app.analytics.periods import Period

RNG = np.random.default_rng(11)


def quantify_stockout_impact(cur: Period, product_id: str, region_id: str | None = None) -> dict:
    """Lost revenue = unserved units x the price those units actually realised.

    The realised price comes from the same product's sales in the same period,
    so discounting is already baked in -- no assumed list price.
    """
    params = {"start": cur.start, "end": cur.end, "product_id": product_id}
    inv_clause = sale_clause = ""
    if region_id:
        inv_clause = " AND region_id = :region_id"
        sale_clause = " AND s.region_id = :region_id"
        params["region_id"] = region_id

    inv = _frame(f"""
        SELECT date AS date, units_sold AS units_sold, units_lost AS units_lost,
               stockout AS stockout
        FROM inventory
        WHERE date BETWEEN :start AND :end AND product_id = :product_id{inv_clause}
    """, params)
    sal = _frame(f"""
        SELECT SUM(s.revenue) AS revenue, SUM(s.quantity) AS quantity,
               SUM(s.profit) AS profit
        FROM sales s
        WHERE s.date BETWEEN :start AND :end AND s.product_id = :product_id{sale_clause}
    """, params)

    units_lost = int(inv.units_lost.sum()) if not inv.empty else 0
    qty = float(sal.quantity.iloc[0] or 0)
    realised_price = float(sal.revenue.iloc[0] or 0) / qty if qty else 0.0
    margin_per_unit = float(sal.profit.iloc[0] or 0) / qty if qty else 0.0

    lost_revenue = units_lost * realised_price
    return {
        "product_id": product_id, "region_id": region_id, "period": cur.as_dict(),
        "unserved_units": units_lost,
        "realised_price_per_unit": round(realised_price, 2),
        "lost_revenue": round(lost_revenue, 2),
        "lost_revenue_display": fmt_inr(lost_revenue),
        "lost_gross_profit": round(units_lost * margin_per_unit, 2),
        # distinct calendar days with a stockout somewhere in scope (not region-days)
        "stockout_days": int(inv.assign(stockout=inv.stockout.astype(bool))
                             .groupby("date").stockout.max().sum()) if not inv.empty else 0,
        "method": "unserved units (inventory.units_lost) x realised price per unit "
                  "(sales.revenue / sales.quantity) for the same product, region and period",
        "caveat": "Assumes unserved demand was lost rather than deferred or substituted; "
                  "treat as an upper bound on the recoverable amount.",
    }


def attribution(total_delta: float, components: list[dict]) -> dict:
    """Split an observed change across quantified components, keeping an explicit
    'unexplained' remainder rather than forcing the parts to sum to the whole."""
    explained = sum(abs(c["amount"]) for c in components)
    rows = [{**c, "share_of_change_pct": round(abs(c["amount"]) / abs(total_delta) * 100, 1)
             if total_delta else None} for c in components]
    remainder = abs(total_delta) - explained
    return {
        "total_change": round(total_delta, 2),
        "components": rows,
        "unexplained": round(remainder, 2),
        "unexplained_pct": round(remainder / abs(total_delta) * 100, 1) if total_delta else None,
    }


def simulate_safety_stock(product_id: str, region_id: str, uplift_pct: float = 15.0,
                          lookback_days: int = 180, trials: int = 4000,
                          holding_cost_rate: float = 0.22) -> dict:
    """What-if: how much stockout risk does extra safety stock actually buy?

    Bootstraps daily demand from the product's own recent history and samples
    supplier lead times from its own purchase-order record, then compares the
    current reorder policy with an uplifted one over a 90-day horizon.
    """
    inv = _frame("""
        SELECT i.date AS date, i.units_sold AS units_sold, i.units_lost AS units_lost
        FROM inventory i
        WHERE i.product_id = :product_id AND i.region_id = :region_id
        ORDER BY i.date DESC LIMIT :n
    """, {"product_id": product_id, "region_id": region_id, "n": lookback_days})
    po = _frame("""
        SELECT po.received_date AS received_date, po.promised_date AS promised_date,
               po.delay_days AS delay_days, su.standard_lead_time_days AS lead
        FROM purchase_orders po JOIN suppliers su ON su.supplier_id = po.supplier_id
        WHERE po.product_id = :product_id AND po.region_id = :region_id
    """, {"product_id": product_id, "region_id": region_id})
    meta = _frame("""
        SELECT p.unit_price AS unit_price, p.unit_cost AS unit_cost
        FROM products p WHERE p.product_id = :product_id
    """, {"product_id": product_id})
    if inv.empty or po.empty or meta.empty:
        return {"error": "insufficient history for simulation"}

    demand = (inv.units_sold + inv.units_lost).to_numpy(dtype=float)
    lead_times = (po.lead + po.delay_days).to_numpy(dtype=float)
    unit_price, unit_cost = float(meta.unit_price.iloc[0]), float(meta.unit_cost.iloc[0])
    mean_daily = float(demand.mean())
    median_lead = float(np.median(lead_times))
    base_safety_days = 3.0
    cover_days = 18.0
    horizon = 90

    def run(safety_days: float) -> tuple[float, float, float]:
        """(-> stockout days, unserved units, average stock on hand) per horizon."""
        reorder_point = mean_daily * (median_lead + safety_days)
        order_qty = mean_daily * (cover_days + safety_days)
        tot_days = tot_lost = tot_stock = 0.0
        for _ in range(trials):
            stock = order_qty
            pipeline: dict[int, float] = {}
            on_order = False
            days = lost = stock_sum = 0.0
            for day in range(horizon):
                if day in pipeline:
                    stock += pipeline.pop(day)
                    on_order = False
                d = float(RNG.choice(demand))
                served = min(d, stock)
                if d > stock:
                    days += 1
                    lost += d - served
                stock -= served
                stock_sum += stock
                if not on_order and stock <= reorder_point:
                    lt = int(RNG.choice(lead_times))
                    pipeline[day + lt] = pipeline.get(day + lt, 0.0) + order_qty
                    on_order = True
            tot_days += days
            tot_lost += lost
            tot_stock += stock_sum / horizon
        return tot_days / trials, tot_lost / trials, tot_stock / trials

    base_days, base_lost, base_stock = run(base_safety_days)
    # "+X% safety stock" is read as X% more days of cover on top of the lead time.
    new_safety = base_safety_days + (uplift_pct / 100) * (median_lead + base_safety_days)
    up_days, up_lost, up_stock = run(new_safety)

    protected_units = max(base_lost - up_lost, 0.0)
    protected_revenue = protected_units * unit_price * 0.92
    extra_stock_units = max(up_stock - base_stock, 0.0)
    extra_holding_cost = extra_stock_units * unit_cost * holding_cost_rate * (horizon / 365)

    return {
        "product_id": product_id, "region_id": region_id,
        "assumption": {
            "horizon_days": horizon, "trials": trials,
            "demand_source": f"bootstrap of the last {len(demand)} observed daily demand values",
            "lead_time_source": f"{len(lead_times)} historical purchase orders "
                                f"(median {median_lead:.0f} days)",
            "holding_cost_rate_pa": holding_cost_rate,
            "safety_days_current": round(base_safety_days, 1),
            "safety_days_simulated": round(new_safety, 1),
        },
        "current_policy": {
            "expected_stockout_days_per_90d": round(base_days, 1),
            "stockout_probability_pct": round(base_days / horizon * 100, 1),
            "expected_unserved_units": round(base_lost, 1),
        },
        "uplifted_policy": {
            "safety_stock_uplift_pct": uplift_pct,
            "expected_stockout_days_per_90d": round(up_days, 1),
            "stockout_probability_pct": round(up_days / horizon * 100, 1),
            "expected_unserved_units": round(up_lost, 1),
        },
        "economics": {
            "protected_revenue": round(protected_revenue, 2),
            "protected_revenue_display": fmt_inr(protected_revenue),
            "additional_holding_cost": round(extra_holding_cost, 2),
            "additional_holding_cost_display": fmt_inr(extra_holding_cost),
            "net_benefit": round(protected_revenue - extra_holding_cost, 2),
            "net_benefit_display": fmt_inr(protected_revenue - extra_holding_cost),
        },
        "caveat": "Simulation inherits the historical lead-time distribution, which includes "
                  "the observed disruption; it is a planning aid, not a forecast.",
    }
