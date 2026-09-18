"""Hypothesis scoring and evidence validation.

The model does not decide what caused the movement.  Each candidate explanation
has an explicit, readable scorer that reads the *facts* gathered during the
investigation and returns:

  status    supported | partial | ruled_out | untested
  score     0-1 strength of evidence  (NOT a probability of causation)
  evidence  the specific numbers, with the table they came from

Ruled-out hypotheses are kept and reported.  An investigation that only says
what the cause was, without saying what it wasn't, is not auditable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.analytics.metrics import fmt_inr

Status = str


@dataclass
class Verdict:
    status: Status = "untested"
    score: float = 0.0
    evidence: list[dict] = field(default_factory=list)
    note: str = ""


@dataclass
class Hypothesis:
    key: str
    label: str
    family: str          # supply | demand | commercial | mix | data
    scorer: Callable[[dict], Verdict]
    upstream_of: str | None = None


def _ev(claim: str, source: str, value: str | None = None) -> dict:
    return {"claim": claim, "source": source, "value": value}


# --------------------------------------------------------------------------
def _inventory(f: dict) -> Verdict:
    fill = f.get("fill_rate_pct")
    days = f.get("stockout_days")
    if fill is None and days is None:
        return Verdict("untested", 0.0, note="inventory ledger not consulted")

    ev = []
    if days:
        streak = f.get("stockout_streak_days")
        window = f.get("stockout_window")
        ev.append(_ev(f"{days} stockout day(s)"
                      + (f", longest run {streak} consecutive days ({window})" if streak else ""),
                      "inventory (daily ledger)", str(days)))
    if f.get("unserved_units"):
        ev.append(_ev(f"{f['unserved_units']} units of demand could not be served",
                      "inventory.units_lost", str(f["unserved_units"])))
    if fill is not None:
        ev.append(_ev(f"fill rate {fill}% against a 97% Class A target",
                      "inventory (served vs demanded)", f"{fill}%"))
    if f.get("lost_revenue"):
        ev.append(_ev(f"unserved demand worth {f.get('lost_revenue_display')} at realised prices",
                      "inventory x sales", f.get("lost_revenue_display")))

    if fill is not None and fill >= 97:
        return Verdict("ruled_out", 0.05, ev, "stock served effectively all demand")
    score = 0.0
    if fill is not None:
        score = 0.95 if fill < 60 else 0.85 if fill < 80 else 0.6 if fill < 95 else 0.15
    elif days:
        score = min(0.35 + 0.03 * days, 0.85)

    # does the quantified loss actually cover the movement it is meant to explain?
    delta, lost = f.get("revenue_delta"), f.get("lost_revenue")
    if delta and lost:
        coverage = abs(lost) / abs(delta)
        ev.append(_ev(f"unserved demand equals {coverage * 100:.0f}% of the total revenue change",
                      "computed", f"{coverage * 100:.0f}%"))
        if coverage < 0.15:
            score = min(score, 0.45)
    status = "supported" if score >= 0.6 else "partial" if score >= 0.3 else "ruled_out"
    return Verdict(status, round(score, 2), ev)


def _supplier(f: dict) -> Verdict:
    cur, base = f.get("supplier_avg_delay_days"), f.get("supplier_baseline_delay_days")
    if cur is None:
        return Verdict("untested", 0.0, note="purchase orders not consulted")
    ev = [_ev(f"average delivery delay {cur} days vs {base} days in the preceding baseline",
              "purchase_orders", f"{cur}d")]
    if f.get("worst_po_delay_days"):
        ev.append(_ev(f"worst consignment {f.get('worst_po_id')} from {f.get('worst_po_supplier')} "
                      f"arrived {f['worst_po_delay_days']} days after the promised date",
                      "purchase_orders", f"{f['worst_po_delay_days']}d"))
    if cur >= 5 or (base and cur >= 2.5 * base):
        ev.append(_ev("above the 5-day escalation threshold in the supplier management policy",
                      "policy", None))
        return Verdict("supported", 0.85 if cur >= 5 else 0.65, ev)
    if cur >= 3:
        return Verdict("partial", 0.4, ev)
    return Verdict("ruled_out", 0.1, ev, "delivery performance within contracted tolerance")


def _marketing(f: dict) -> Verdict:
    chg = f.get("marketing_spend_pct_change_scoped", f.get("marketing_spend_pct_change"))
    if chg is None:
        return Verdict("untested", 0.0, note="marketing spend not consulted")
    scope = f.get("marketing_scope", "company-wide")
    ev = [_ev(f"marketing spend {chg:+.1f}% ({scope})", "marketing", f"{chg:+.1f}%")]
    if chg <= -25:
        ev.append(_ev("beyond the 20% budget-variance floor; at a 0.15-0.25 elasticity this implies "
                      "roughly 4-8% less demand in the same month", "policy + marketing", None))
        return Verdict("supported", 0.55, ev, "contributing driver, smaller than the supply effect")
    if chg <= -10:
        return Verdict("partial", 0.3, ev)
    return Verdict("ruled_out", 0.08, ev, "spend broadly stable")


def _pricing(f: dict) -> Verdict:
    pp = f.get("discount_pp_change")
    if pp is None:
        return Verdict("untested", 0.0, note="pricing not consulted")
    rp = f.get("realised_price_pct_change")
    ev = [_ev(f"average discount moved {pp:+.2f} percentage points", "sales.discount_pct", f"{pp:+.2f}pt")]
    if rp is not None:
        ev.append(_ev(f"realised price per unit {rp:+.1f}%", "sales.revenue / sales.quantity", f"{rp:+.1f}%"))
    if abs(pp) >= 2:
        return Verdict("supported", 0.6, ev)
    ev.append(_ev("within the 2 percentage-point tolerance in the pricing policy", "policy", None))
    note = "discounting stable"
    if rp is not None and rp <= -3:
        note = ("realised price fell while discount held: a mix effect (expensive lines sold less), "
                "not a pricing action")
    return Verdict("ruled_out", 0.1, ev, note)


def _customers(f: dict) -> Verdict:
    chg = f.get("active_customers_pct_change")
    if chg is None:
        return Verdict("untested", 0.0, note="customer activity not consulted")
    ev = [_ev(f"active customers {chg:+.1f}%", "sales x customers", f"{chg:+.1f}%")]
    if chg <= -10:
        return Verdict("supported", 0.6, ev)
    if chg <= -4:
        return Verdict("partial", 0.3, ev)
    return Verdict("ruled_out", 0.1, ev, "customer base broadly stable")


def _demand_softness(f: dict) -> Verdict:
    fill, units = f.get("fill_rate_pct"), f.get("units_pct_change")
    if fill is None or units is None:
        return Verdict("untested", 0.0)
    ev = [_ev(f"units {units:+.1f}% with a {fill}% fill rate", "sales + inventory", f"{units:+.1f}%")]
    if fill >= 97 and units <= -5:
        return Verdict("supported", 0.6, ev, "demand itself weakened; supply was not the constraint")
    if fill < 90:
        return Verdict("ruled_out", 0.1, ev,
                       "measured demand includes unserved orders, so the shortfall is supply-side")
    return Verdict("partial", 0.25, ev)


HYPOTHESES = [
    Hypothesis("inventory_stockout", "Inventory shortage (stockout of a top-selling line)",
               "supply", _inventory),
    Hypothesis("supplier_delay", "Supplier delivery delay upstream of the stockout",
               "supply", _supplier, upstream_of="inventory_stockout"),
    Hypothesis("marketing_reduction", "Reduced marketing investment", "demand", _marketing),
    Hypothesis("pricing_discounting", "Price or discount change", "commercial", _pricing),
    Hypothesis("customer_churn", "Customer base contraction", "demand", _customers),
    Hypothesis("demand_softness", "Underlying demand softness", "demand", _demand_softness),
]


def evaluate(facts: dict) -> list[dict]:
    out = []
    for h in HYPOTHESES:
        v = h.scorer(facts or {})
        out.append({
            "key": h.key, "label": h.label, "family": h.family,
            "status": v.status, "score": v.score, "evidence": v.evidence,
            "note": v.note, "upstream_of": h.upstream_of,
        })
    order = {"supported": 0, "partial": 1, "untested": 2, "ruled_out": 3}
    out.sort(key=lambda h: (order[h["status"]], -h["score"]))
    return out


def causal_chain(facts: dict, hypotheses: list[dict]) -> list[dict]:
    """Assemble the mechanism, one measured link at a time.  Only links that have
    a number behind them are included."""
    supported = {h["key"] for h in hypotheses if h["status"] in ("supported", "partial")}
    chain: list[dict] = []
    if "supplier_delay" in supported and facts.get("worst_po_delay_days"):
        chain.append({"step": "Supplier delay",
                      "detail": f"{facts.get('worst_po_supplier')} delivered {facts['worst_po_delay_days']} "
                                f"days late ({facts.get('worst_po_id')})",
                      "source": "purchase_orders"})
    if "inventory_stockout" in supported and facts.get("stockout_days"):
        chain.append({"step": "Stock ran out",
                      "detail": f"{facts['stockout_days']} stockout day(s)"
                                + (f", {facts.get('stockout_window')}" if facts.get("stockout_window") else ""),
                      "source": "inventory"})
    if facts.get("fill_rate_pct") is not None:
        chain.append({"step": "Demand could not be served",
                      "detail": f"fill rate {facts['fill_rate_pct']}%, "
                                f"{facts.get('unserved_units', 0)} units unserved",
                      "source": "inventory.units_lost"})
    if facts.get("worst_product_label"):
        chain.append({"step": "Product revenue fell",
                      "detail": f"{facts['worst_product_label']} {facts.get('worst_product_pct')}% "
                                f"({fmt_inr(facts.get('worst_product_delta'))})",
                      "source": "sales"})
    if facts.get("worst_region_label"):
        chain.append({"step": "Region revenue fell",
                      "detail": f"{facts['worst_region_label']} {facts.get('worst_region_pct')}% "
                                f"({fmt_inr(facts.get('worst_region_delta'))}), "
                                f"{facts.get('worst_region_share_of_decline')}% of the total decline",
                      "source": "sales"})
    if facts.get("revenue_pct_change") is not None:
        chain.append({"step": "Company revenue fell",
                      "detail": f"{facts['revenue_pct_change']}% total "
                                f"({facts.get('revenue_per_day_pct_change')}% per day), "
                                f"{fmt_inr(facts.get('revenue_delta'))}",
                      "source": "sales"})
    return chain


def overall_confidence(hypotheses: list[dict], facts: dict) -> tuple[float, list[str]]:
    """Confidence in the *conclusion*, with the reasons stated."""
    supported = [h for h in hypotheses if h["status"] == "supported"]
    reasons: list[str] = []
    if not supported:
        return 0.25, ["no hypothesis reached the evidence threshold"]
    top = max(supported, key=lambda h: h["score"])
    conf = top["score"]
    reasons.append(f"strongest hypothesis '{top['label']}' scored {top['score']}")

    ruled = [h for h in hypotheses if h["status"] == "ruled_out"]
    if len(ruled) >= 2:
        conf += 0.03 * min(len(ruled), 2)
        reasons.append(f"{len(ruled)} alternative explanation(s) tested and ruled out")

    delta, lost = facts.get("revenue_delta"), facts.get("lost_revenue")
    if delta and lost:
        coverage = min(abs(lost) / abs(delta), 1.0)
        reasons.append(f"the quantified impact covers {coverage * 100:.0f}% of the total movement "
                       f"(the remainder sits with the secondary drivers and normal variation)")
        if coverage < 0.3:
            conf = min(conf, 0.55)
        elif coverage < 0.5:
            conf = min(conf, 0.8)
    else:
        conf = min(conf, 0.7)
        reasons.append("impact not quantified in currency terms")

    # A single month of evidence never justifies near-certainty.
    conf = min(conf, 0.92)

    untested = [h for h in hypotheses if h["status"] == "untested"]
    if untested:
        conf = min(conf, 0.9)
        reasons.append(f"{len(untested)} hypothesis/hypotheses left untested: "
                       + ", ".join(h["key"] for h in untested))
    return round(conf, 2), reasons
