"""Recommendations, narration and the final report object.

Recommendations are assembled from *supported* hypotheses only, and every one of
them carries: the evidence it rests on, the policy clause that sets the
threshold, the expected effect where it could be simulated, and an explicit
human-approval flag.  Nothing here is autonomous: the agent proposes.
"""
from __future__ import annotations

from typing import Any

from app.agents.knowledge import search as policy_search
from app.agents.llm import get_llm
from app.analytics.metrics import fmt_inr

NARRATOR_SYSTEM = """You are writing the executive summary of a completed business
investigation for a category manager.

Hard rules:
- Use ONLY the figures in the payload. Never introduce, adjust or recompute a number.
- If something was ruled out, say so explicitly - that is the valuable part.
- Describe evidence as evidence: say what was measured and over what period. Do not
  claim proof of causation beyond the measured mechanism.
- 4 short paragraphs at most, no bullet lists, no headings, plain business English.
"""


def _by_tool(findings: list[dict], tool: str) -> list[dict]:
    return [f for f in findings if f.get("tool") == tool and not f.get("error")]


def build_recommendations(facts: dict, hypotheses: list[dict], findings: list[dict]) -> list[dict]:
    supported = {h["key"]: h for h in hypotheses if h["status"] in ("supported", "partial")}
    product = facts.get("worst_product_label") or facts.get("worst_product") or "the affected line"
    product_id = facts.get("worst_product") or ""
    region = facts.get("worst_region_label") or facts.get("worst_region") or "the affected region"
    recs: list[dict] = []

    sim = _by_tool(findings, "simulate_safety_stock")
    sim_data = sim[-1]["data"] if sim else {}

    if "inventory_stockout" in supported:
        eco = (sim_data or {}).get("economics", {})
        expected = None
        if eco:
            up = sim_data.get("uplifted_policy", {})
            cur = sim_data.get("current_policy", {})
            expected = (f"stockout risk {cur.get('stockout_probability_pct')}% -> "
                        f"{up.get('stockout_probability_pct')}%, net "
                        f"{eco.get('net_benefit_display')} per 90 days (simulated)")
        recs.append({
            "priority": 1,
            "action": f"Raise safety stock for {product} in {region} to the Class A minimum "
                      f"(15% of lead-time demand, never below 5 days of cover) and add the 3-day "
                      f"import buffer.",
            "why": f"{facts.get('unserved_units', 0)} units of demand went unserved over "
                   f"{facts.get('stockout_days', 0)} stockout day(s); fill rate "
                   f"{facts.get('fill_rate_pct')}% against a 97% target.",
            "expected_effect": expected,
            "policy": _cite("safety stock norms class A minimum days of cover"),
            "owner": "Supply planning",
            "approval_required": True,
        })
        recs.append({
            "priority": 2,
            "action": "Enable a low-stock alert at 7 days of forecast cover, with a critical "
                      "escalation at 3 days, for every Class A imported line.",
            "why": "The shortage was visible in the ledger days before revenue moved; nothing "
                   "escalated until the month closed.",
            "expected_effect": "Converts a month-end discovery into a same-week intervention.",
            "policy": _cite("low stock alert threshold 7 days critical alert"),
            "owner": "Supply planning / BI",
            "approval_required": False,
        })
        recs.append({
            "priority": 4,
            "action": f"Cover the immediate gap by inter-warehouse transfer into {region} from any "
                      f"warehouse holding more than 20 days of cover before ordering air freight.",
            "why": "Policy sets transfer as the first response to a single-region zero-stock event.",
            "expected_effect": None,
            "policy": _cite("inter-warehouse stock transfer emergency measures"),
            "owner": "Logistics",
            "approval_required": True,
        })

    if "supplier_delay" in supported:
        recs.append({
            "priority": 3,
            "action": f"Escalate formally to {facts.get('worst_po_supplier', 'the supplier')} and require "
                      f"a written recovery plan; plan future cover on the 85th-percentile lead time "
                      f"rather than the contracted one.",
            "why": f"Average delay {facts.get('supplier_avg_delay_days')} days against "
                   f"{facts.get('supplier_baseline_delay_days')} days baseline, worst consignment "
                   f"{facts.get('worst_po_delay_days')} days late ({facts.get('worst_po_id')}).",
            "expected_effect": "Removes the recurrence risk at source; qualifies a second supplier if "
                               "reliability stays below 0.90.",
            "policy": _cite("supplier escalation threshold average delay dual sourcing"),
            "owner": "Procurement",
            "approval_required": True,
        })

    if "marketing_reduction" in supported:
        recs.append({
            "priority": 5,
            "action": f"Restore, or formally re-approve, the {region} marketing budget before the next "
                      f"cycle, and record the expected demand impact.",
            "why": f"Spend moved {facts.get('marketing_spend_pct_change_scoped', facts.get('marketing_spend_pct_change'))}% "
                   f"in {region}, beyond the 20% variance floor.",
            "expected_effect": "At a 0.15-0.25 elasticity, restoring spend recovers roughly 4-8% of "
                               "category demand in the same month.",
            "policy": _cite("marketing budget variance floor approval elasticity"),
            "owner": "Regional marketing",
            "approval_required": True,
        })

    recs.append({
        "priority": 6,
        "action": "Add fill rate by Class A product-region, and supplier lead-time variance, to the "
                  "weekly operating review.",
        "why": "Both signals moved before revenue did, and neither is on the current dashboard.",
        "expected_effect": "Earlier detection of the same failure mode.",
        "policy": _cite("monitoring supplier lead time variance weekly service level"),
        "owner": "BI",
        "approval_required": False,
    })
    recs.sort(key=lambda r: r["priority"])
    return recs


def _cite(query: str) -> dict | None:
    hits = policy_search(query, k=1)
    if not hits:
        return None
    h = hits[0]
    return {"document": h["document"], "policy": h["policy"], "section": h["section"],
            "excerpt": h["excerpt"][:280]}


# --------------------------------------------------------------------------
def template_narrative(state: dict) -> str:
    f = state.get("facts", {})
    cur = state.get("current_period", {}).get("label", "the current period")
    prev = state.get("comparison_period", {}).get("label", "the prior period")
    top = next((h for h in state.get("hypotheses", []) if h["status"] == "supported"), None)
    ruled = [h["label"] for h in state.get("hypotheses", []) if h["status"] == "ruled_out"]

    parts = []
    if f.get("revenue_pct_change") is not None:
        parts.append(
            f"Revenue in {cur} was {fmt_inr(f.get('revenue_delta'))} against {prev} "
            f"({f['revenue_pct_change']}% in total, {f.get('revenue_per_day_pct_change')}% on a "
            f"per-day basis, which is the like-for-like comparison because the two months differ "
            f"in length).")
    if f.get("worst_region_label"):
        parts.append(
            f"The movement is concentrated: {f['worst_region_label']} accounts for "
            f"{f.get('worst_region_share_of_decline')}% of the decline "
            f"({f.get('worst_region_pct')}%), and inside it {f.get('worst_product_label', 'one line')} "
            f"moved {f.get('worst_product_pct')}%.")
    if f.get("fill_rate_pct") is not None:
        parts.append(
            f"This was a supply constraint rather than a demand shift: the fill rate was "
            f"{f['fill_rate_pct']}% with {f.get('unserved_units', 0)} units of demand recorded as "
            f"unserved over {f.get('stockout_days', 0)} stockout day(s)"
            + (f", traced upstream to a {f.get('worst_po_delay_days')}-day late consignment "
               f"({f.get('worst_po_id')}) from {f.get('worst_po_supplier')}."
               if f.get("worst_po_delay_days") else "."))
    if f.get("lost_revenue_display"):
        parts.append(f"The unserved demand is worth {f['lost_revenue_display']} at realised prices.")
    if ruled:
        parts.append("Ruled out on the evidence: " + "; ".join(ruled[:3]) + ".")
    if top:
        parts.append(f"Most strongly supported explanation: {top['label']} (evidence score "
                     f"{top['score']}).")
    return " ".join(parts)


def narrate(state: dict) -> tuple[str, str]:
    """Returns (narrative, source) where source is 'llm' or 'template'."""
    llm = get_llm()
    payload = {
        "question": state.get("question"),
        "current_period": state.get("current_period"),
        "comparison_period": state.get("comparison_period"),
        "validated_figures": {k: v for k, v in state.get("facts", {}).items() if v is not None},
        "findings": [f["summary"] for f in state.get("findings", [])],
        "hypotheses": [{k: h[k] for k in ("label", "status", "score", "note")}
                       for h in state.get("hypotheses", [])],
        "causal_chain": state.get("causal_chain", []),
        "confidence": state.get("confidence"),
    }
    import json
    text = llm.write(NARRATOR_SYSTEM, json.dumps(payload, indent=1, default=str))
    if text:
        return text, "llm"
    return template_narrative(state), "template"


def charts_from(findings: list[dict]) -> dict:
    """Pull the series the dashboard draws straight out of the tool results."""
    charts: dict[str, Any] = {}
    tr = _by_tool(findings, "get_trend")
    if tr:
        charts["revenue_trend"] = tr[0]["data"].get("points", [])
    for f in _by_tool(findings, "get_breakdown"):
        dim = f["data"].get("dimension")
        scoped = "region_id" in (f.get("args") or {})
        key = f"breakdown_{dim}" + ("_scoped" if scoped else "")
        charts.setdefault(key, {"rows": f["data"].get("rows", []), "args": f.get("args", {})})
    inv = _by_tool(findings, "get_inventory_health")
    if inv:
        charts["inventory_daily"] = inv[-1]["data"].get("daily", [])
        charts["inventory_scope"] = inv[-1].get("args", {})
    anom = _by_tool(findings, "detect_anomalies")
    if anom:
        charts["anomalies"] = anom[-1]["data"].get("entities", [])[:12]
    sup = _by_tool(findings, "get_supplier_performance")
    if sup:
        charts["purchase_orders"] = sup[-1]["data"].get("worst_purchase_orders", [])
    sim = _by_tool(findings, "simulate_safety_stock")
    if sim:
        charts["simulation"] = sim[-1]["data"]
    return charts


def build_report(state: dict) -> dict:
    f = state.get("facts", {})
    return {
        "run_id": state.get("run_id"),
        "question": state.get("question"),
        "objective": state.get("objective"),
        "intent": state.get("intent"),
        "planner": state.get("planner"),
        "llm": state.get("llm"),
        "period": state.get("current_period"),
        "comparison": state.get("comparison_period"),
        "headline": {
            "revenue_change_pct": f.get("revenue_pct_change"),
            "revenue_change_per_day_pct": f.get("revenue_per_day_pct_change"),
            "revenue_delta": f.get("revenue_delta"),
            "revenue_delta_display": fmt_inr(f.get("revenue_delta")) if f.get("revenue_delta") else None,
            "primary_region": f.get("worst_region_label"),
            "primary_region_share_of_decline_pct": f.get("worst_region_share_of_decline"),
            "primary_product": f.get("worst_product_label"),
            "primary_product_change_pct": f.get("worst_product_pct"),
            "stockout_days": f.get("stockout_days"),
            "fill_rate_pct": f.get("fill_rate_pct"),
            "estimated_impact": f.get("lost_revenue_display"),
        },
        "root_cause": state.get("root_cause"),
        "causal_chain": state.get("causal_chain", []),
        "hypotheses": state.get("hypotheses", []),
        "confidence": state.get("confidence"),
        "confidence_reasons": state.get("confidence_reasons", []),
        "narrative": state.get("narrative"),
        "narrative_source": state.get("narrative_source"),
        "recommendations": state.get("recommendations", []),
        "findings": [{k: v for k, v in fnd.items() if k != "data"} for fnd in state.get("findings", [])],
        "charts": charts_from(state.get("findings", [])),
        "steps_used": state.get("steps_used"),
        "warnings": state.get("warnings", []),
        "data_notice": "All figures come from a synthetic demonstration dataset.",
    }
