"""Synthetic dataset generator.

This is a *mechanistic* generator, not a bag of random numbers: daily demand is
simulated, inventory is depleted by that demand, purchase orders are placed
against supplier lead times, and sales are the portion of demand that inventory
could actually serve.  A supplier delay therefore genuinely *causes* a stockout,
which genuinely *causes* the revenue decline the agent has to discover.

Planted storyline (July 2026 vs June 2026)
------------------------------------------
  1. PRIMARY   AirTech Components (SUP03) consignments ordered from mid-June are
               ~3 weeks late into the northern/western hubs -> SmartAir Purifier
               3000i (P103) and the rest of the air-care line run to zero stock
               -> demand cannot be served -> revenue is lost.
  2. SECONDARY North marketing spend is cut ~32% in July, and the air-care line
               in North is cut a further ~30% on top -> softer demand there.
  3. NOISE     Mild unexplained softness in East, plus ordinary daily noise.
  4. DECOYS    Pricing and discounting are stable; customer mix is stable;
               other suppliers are on time.  These must be ruled out, not blamed.
"""
from __future__ import annotations

import argparse
import math
from datetime import date, timedelta

import numpy as np
from sqlalchemy import insert

from app.config import settings
from app.data import catalog as cat
from app.db import models as m
from app.db.session import rw_engine

# --------------------------------------------------------------------------
# planted events
# --------------------------------------------------------------------------
# A customs / port hold on AirTech consignments: anything that was *due* inside
# the hold window is only released on a fixed date, and the northern and western
# inbound hubs are released last.  Modelling it on the arrival side (rather than
# as extra lead-time days) keeps the disruption deterministic and auditable.
SUPPLIER_DELAY = {
    "supplier_id": cat.HERO_SUPPLIER,
    "hold_window": (date(2026, 6, 30), date(2026, 7, 17)),
    "release_date": {"WH-N": date(2026, 7, 18), "WH-W": date(2026, 7, 17)},
    "default_release_date": date(2026, 7, 9),
}
MARKETING_CUT = {
    "region_id": "NORTH",
    "months": [(2026, 7)],
    "region_factor": 0.68,          # region-wide budget reallocation
    "category": "Home Environment",
    "category_factor": 0.70,        # compounding cut on the air-care line
}
EAST_SOFTNESS = {"region_id": "EAST", "months": [(2026, 7)], "factor": 0.94}

MKT_ELASTICITY = 0.22       # demand lift = (spend / baseline) ** elasticity
AVG_DISCOUNT = 0.08
MONTHLY_TREND = 0.006


def _weekday_factor(d: date) -> float:
    return {5: 1.18, 6: 1.16, 4: 1.05}.get(d.weekday(), 0.95)


def _promo_bonus(d: date) -> float:
    """Festive season discounting (Oct/Nov) -- deliberately outside the Jun/Jul
    comparison window so it cannot confound the demo question."""
    return 0.06 if d.month in (10, 11) else 0.0


def daterange(start: date, end: date) -> list[date]:
    n = (end - start).days + 1
    return [start + timedelta(days=i) for i in range(n)]


class Generator:
    def __init__(self, seed: int, start: date, end: date):
        self.rng = np.random.default_rng(seed)
        self.days = daterange(start, end)
        self.start, self.end = start, end
        share_sum = sum(p[7] for p in cat.PRODUCTS)
        self.products = {
            p[0]: {
                "product_id": p[0], "product_name": p[1], "category": p[2], "subcategory": p[3],
                "unit_price": float(p[4]), "unit_cost": float(p[5]), "supplier_id": p[6],
                "share": p[7] / share_sum, "season": p[8], "cover_days": p[9], "safety_days": p[10],
            }
            for p in cat.PRODUCTS
        }
        self.regions = {r[0]: {"region_id": r[0], "region_name": r[1], "country": r[2],
                               "warehouse_id": r[3], "weight": r[4]} for r in cat.REGIONS}
        self.suppliers = {s[0]: {"supplier_id": s[0], "supplier_name": s[1], "country": s[2],
                                 "standard_lead_time_days": s[3], "reliability_score": s[4]}
                          for s in cat.SUPPLIERS}

    # ---------------- dimensions -----------------------------------------
    def customers(self, n: int = 9000) -> list[dict]:
        seg_names = [s[0] for s in cat.SEGMENTS]
        seg_p = np.array([s[1] for s in cat.SEGMENTS])
        reg_ids = list(self.regions)
        reg_p = np.array([self.regions[r]["weight"] for r in reg_ids])
        ag_names = [a[0] for a in cat.AGE_GROUPS]
        ag_p = np.array([a[1] for a in cat.AGE_GROUPS])
        ac_names = [a[0] for a in cat.ACQUISITION_CHANNELS]
        ac_p = np.array([a[1] for a in cat.ACQUISITION_CHANNELS])
        span = (self.end - self.start).days
        rows = []
        for i in range(n):
            if self.rng.random() < 0.55:
                signup = self.start - timedelta(days=int(self.rng.integers(0, 900)))
            else:
                signup = self.start + timedelta(days=int(self.rng.integers(0, span)))
            rows.append({
                "customer_id": f"C{100000 + i}",
                "segment": seg_names[int(self.rng.choice(len(seg_names), p=seg_p))],
                "region_id": reg_ids[int(self.rng.choice(len(reg_ids), p=reg_p))],
                "age_group": ag_names[int(self.rng.choice(len(ag_names), p=ag_p))],
                "acquisition_channel": ac_names[int(self.rng.choice(len(ac_names), p=ac_p))],
                "signup_date": signup,
            })
        return rows

    # ---------------- marketing ------------------------------------------
    def marketing(self) -> tuple[list[dict], dict]:
        """Monthly spend per product x region x channel, plus the spend index the
        demand model consumes."""
        months = sorted({(d.year, d.month) for d in self.days})
        rows: list[dict] = []
        index: dict = {}
        mkt_channels = {"Paid Search": 0.45, "Social": 0.33, "Retail Co-op": 0.22}
        for pid, p in self.products.items():
            for rid, r in self.regions.items():
                base_monthly_rev = cat.TARGET_DAILY_REVENUE * p["share"] * r["weight"] * 30.44
                baseline = 0.055 * base_monthly_rev
                for (y, mo) in months:
                    factor = float(self.rng.normal(1.0, 0.06))
                    if rid == MARKETING_CUT["region_id"] and (y, mo) in MARKETING_CUT["months"]:
                        factor *= MARKETING_CUT["region_factor"]
                        if p["category"] == MARKETING_CUT["category"]:
                            factor *= MARKETING_CUT["category_factor"]
                    if mo in (10, 11):
                        factor *= 1.35
                    spend = max(baseline * factor, 1.0)
                    index[(pid, rid, y, mo)] = spend / baseline
                    for ch, share in mkt_channels.items():
                        s = spend * share
                        cpm = float(self.rng.uniform(180, 320))
                        impressions = int(s / cpm * 1000)
                        clicks = int(impressions * float(self.rng.uniform(0.008, 0.021)))
                        conversions = int(clicks * float(self.rng.uniform(0.02, 0.06)))
                        rows.append({
                            "campaign_id": f"CMP-{pid}-{rid}-{y}{mo:02d}-{ch[:2].upper()}",
                            "date": date(y, mo, 1), "product_id": pid, "region_id": rid,
                            "channel": ch, "spend": round(s, 2), "impressions": impressions,
                            "clicks": clicks, "conversions": conversions,
                        })
        return rows, index

    # ---------------- demand ---------------------------------------------
    def demand(self, mkt_index: dict) -> dict:
        """Expected daily unit demand per (product, region) as a numpy array."""
        out = {}
        for pid, p in self.products.items():
            eff_price = p["unit_price"] * (1 - AVG_DISCOUNT)
            nat_units = cat.TARGET_DAILY_REVENUE * p["share"] / eff_price
            season = cat.SEASONALITY[p["season"]]
            for rid, r in self.regions.items():
                base = nat_units * r["weight"]
                vals = np.empty(len(self.days))
                for i, d in enumerate(self.days):
                    months_in = (d.year - self.start.year) * 12 + (d.month - self.start.month)
                    f = base
                    f *= season[d.month - 1]
                    f *= _weekday_factor(d)
                    f *= (1 + MONTHLY_TREND) ** months_in
                    f *= mkt_index[(pid, rid, d.year, d.month)] ** MKT_ELASTICITY
                    if rid == EAST_SOFTNESS["region_id"] and (d.year, d.month) in EAST_SOFTNESS["months"]:
                        f *= EAST_SOFTNESS["factor"]
                    vals[i] = f
                noise = self.rng.lognormal(mean=0.0, sigma=0.16, size=len(self.days))
                out[(pid, rid)] = np.maximum(vals * noise, 0.0)
        return out

    # ---------------- inventory + fulfilment ------------------------------
    def simulate_inventory(self, demand: dict):
        """Day-by-day stock simulation.  Returns inventory rows, PO rows and the
        served-units matrix that sales are built from."""
        inv_rows: list[dict] = []
        po_rows: list[dict] = []
        served: dict = {}
        po_seq = 0
        for pid, p in self.products.items():
            sup = self.suppliers[p["supplier_id"]]
            lead = sup["standard_lead_time_days"]
            for rid, r in self.regions.items():
                exp = demand[(pid, rid)]
                mean_daily = float(exp.mean())
                stock = max(int(round(mean_daily * p["cover_days"])), 5)
                arrivals: dict[int, int] = {}
                open_po = False
                sold_arr = np.zeros(len(self.days), dtype=int)
                trailing: list[float] = []
                for i, d in enumerate(self.days):
                    received = arrivals.pop(i, 0)
                    if received:
                        open_po = False
                    opening = stock
                    available = opening + received
                    want = int(self.rng.poisson(exp[i]))
                    sold = min(want, available)
                    lost = want - sold
                    closing = available - sold
                    sold_arr[i] = sold
                    inv_rows.append({
                        "date": d, "product_id": pid, "warehouse_id": r["warehouse_id"],
                        "region_id": rid, "opening_stock": opening, "units_received": received,
                        "units_sold": sold, "units_lost": lost, "closing_stock": closing,
                        "stockout": bool(lost > 0 or closing == 0),
                    })
                    trailing.append(float(want))
                    avg = float(np.mean(trailing[-28:])) if trailing else mean_daily
                    reorder_point = avg * (lead + p["safety_days"])
                    if not open_po and closing <= reorder_point:
                        qty = int(math.ceil(avg * p["cover_days"]))
                        actual_lead = lead + int(self.rng.integers(0, 3))
                        if self.rng.random() > sup["reliability_score"]:
                            actual_lead += int(self.rng.integers(2, 6))
                        promised = d + timedelta(days=lead)
                        arrival = d + timedelta(days=actual_lead)
                        if (sup["supplier_id"] == SUPPLIER_DELAY["supplier_id"]
                                and SUPPLIER_DELAY["hold_window"][0] <= promised
                                <= SUPPLIER_DELAY["hold_window"][1]):
                            released = SUPPLIER_DELAY["release_date"].get(
                                r["warehouse_id"], SUPPLIER_DELAY["default_release_date"])
                            arrival = max(arrival, released)
                        eta = i + (arrival - d).days
                        if eta < len(self.days):
                            arrivals[eta] = arrivals.get(eta, 0) + qty
                        open_po = True
                        po_seq += 1
                        po_rows.append({
                            "po_id": f"PO-{po_seq:06d}", "order_date": d, "product_id": pid,
                            "supplier_id": sup["supplier_id"], "warehouse_id": r["warehouse_id"],
                            "region_id": rid, "quantity": qty,
                            "promised_date": promised, "received_date": arrival,
                            "delay_days": (arrival - promised).days,
                        })
                    stock = closing
                served[(pid, rid)] = sold_arr
        return inv_rows, po_rows, served

    # ---------------- sales ----------------------------------------------
    def sales(self, served: dict, customers: list[dict]) -> list[dict]:
        by_region: dict[str, list[str]] = {r: [] for r in self.regions}
        seg_of: dict[str, str] = {}
        for c in customers:
            by_region[c["region_id"]].append(c["customer_id"])
            seg_of[c["customer_id"]] = c["segment"]
        cust_arr = {r: np.array(v) for r, v in by_region.items()}
        seg_appetite = {s[0]: s[3] for s in cat.SEGMENTS}
        seg_units = {s[0]: s[2] for s in cat.SEGMENTS}
        ch_ids = [c[0] for c in cat.CHANNELS]
        ch_p = np.array([c[2] for c in cat.CHANNELS])
        rows: list[dict] = []
        for (pid, rid), arr in served.items():
            p = self.products[pid]
            for i, d in enumerate(self.days):
                remaining = int(arr[i])
                if remaining <= 0:
                    continue
                promo = _promo_bonus(d)
                while remaining > 0:
                    cid = str(self.rng.choice(cust_arr[rid]))
                    seg = seg_of[cid]
                    size = 1 + int(self.rng.poisson(max(seg_units[seg] - 1, 0.05)))
                    qty = min(remaining, max(size, 1))
                    remaining -= qty
                    ch = ch_ids[int(self.rng.choice(len(ch_ids), p=ch_p))]
                    disc = (seg_appetite[seg] + promo + (0.03 if ch == "CH02" else 0.0)
                            + float(self.rng.normal(0, 0.02)))
                    disc = float(np.clip(disc, 0.0, 0.35))
                    revenue = qty * p["unit_price"] * (1 - disc)
                    cost = qty * p["unit_cost"]
                    rows.append({
                        "date": d, "product_id": pid, "customer_id": cid, "region_id": rid,
                        "channel_id": ch, "quantity": qty, "unit_price": p["unit_price"],
                        "discount_pct": round(disc, 4), "revenue": round(revenue, 2),
                        "cost": round(cost, 2), "profit": round(revenue - cost, 2),
                    })
        return rows


def _chunked_insert(conn, table, rows, size=5000):
    for i in range(0, len(rows), size):
        conn.execute(insert(table), rows[i:i + size])


def build(seed: int | None = None, start: str | None = None, end: str | None = None) -> dict:
    seed = seed if seed is not None else settings.seed
    start_d = date.fromisoformat(start or settings.history_start)
    end_d = date.fromisoformat(end or settings.history_end)

    g = Generator(seed, start_d, end_d)
    customers = g.customers()
    mkt_rows, mkt_index = g.marketing()
    demand = g.demand(mkt_index)
    inv_rows, po_rows, served = g.simulate_inventory(demand)
    sale_rows = g.sales(served, customers)

    eng = rw_engine()
    m.metadata.drop_all(eng)
    m.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(insert(m.regions), [
            {"region_id": r[0], "region_name": r[1], "country": r[2], "warehouse_id": r[3]}
            for r in cat.REGIONS])
        conn.execute(insert(m.suppliers), [
            {"supplier_id": s[0], "supplier_name": s[1], "country": s[2],
             "standard_lead_time_days": s[3], "reliability_score": s[4]} for s in cat.SUPPLIERS])
        conn.execute(insert(m.channels), [
            {"channel_id": c[0], "channel_name": c[1]} for c in cat.CHANNELS])
        conn.execute(insert(m.products), [
            {"product_id": p[0], "product_name": p[1], "category": p[2], "subcategory": p[3],
             "unit_price": float(p[4]), "unit_cost": float(p[5]), "supplier_id": p[6],
             "launch_date": start_d - timedelta(days=400)} for p in cat.PRODUCTS])
        _chunked_insert(conn, m.customers, customers)
        _chunked_insert(conn, m.marketing, mkt_rows)
        _chunked_insert(conn, m.purchase_orders, po_rows)
        _chunked_insert(conn, m.inventory, inv_rows)
        _chunked_insert(conn, m.sales, sale_rows)

    return {"customers": len(customers), "marketing": len(mkt_rows),
            "purchase_orders": len(po_rows), "inventory": len(inv_rows), "sales": len(sale_rows)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate the synthetic BI dataset")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    counts = build(a.seed, a.start, a.end)
    total = sum(counts.values())
    for k, v in counts.items():
        print(f"  {k:16s} {v:>8,}")
    print(f"  {'TOTAL':16s} {total:>8,}")
