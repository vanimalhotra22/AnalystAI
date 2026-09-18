"""Planning: what to investigate next.

Two interchangeable planners sit behind one interface:

  LLMPlanner        the model reads the question and everything found so far and
                    picks the next tool call.  This is the product behaviour.
  HeuristicPlanner  an explicit investigation policy: the same branching an
                    analyst would follow, encoded as guarded steps.  It runs when
                    no API key is configured, and it catches the LLM planner if a
                    call fails mid-run.

Both drive the *same* tool layer and feed the *same* evidence scorer, so an
investigation is reproducible either way -- only the choice of next step differs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import text

from app.agents import tools as T
from app.agents.llm import get_llm
from app.analytics.metrics import fmt_inr
from app.db.session import ro_engine

INTENTS = ("root_cause", "descriptive", "action", "what_if")

_WHY = re.compile(
    r"\b(why|caus\w+|reason\w*|driver\w*|drove|explain\w*|behind|root|attribut\w*|"
    r"responsible|underperform\w*|led to|down to)\b", re.I)
_ACTION = re.compile(
    r"\b(what should|recommend\w*|action\w*|do about|fix|next step|advice|"
    r"prevent\w*|avoid\w*|stop (this|it|that))\b", re.I)
_WHATIF = re.compile(
    r"\b(what if|simulate|scenario|if we (increase|raise|add)|impact of increasing)\b", re.I)
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")

_MONTHS_RE = ("january|february|march|april|may|june|july|august|september|october|november|december"
              "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_PERIOD_RE = re.compile(
    rf"\b(\d{{4}}-\d{{1,2}}|q[1-4]\s*\d{{4}}|q[1-4]|(?:{_MONTHS_RE})\s*\d{{4}}?|"
    rf"last month|previous month|this month|current month|last \d+ days|ytd)\b", re.I)
_SPLIT_RE = re.compile(r"\b(?:versus|vs\.?|compared (?:to|with)|against|relative to)\b", re.I)
_YOY_RE = re.compile(r"\b(same (?:month|period) last year|year[- ]on[- ]year|yoy|last year)\b", re.I)


def extract_periods(question: str) -> tuple[str | None, str | None]:
    """Pull an explicit period (and comparison) out of the question text, so
    'What was revenue in June 2026?' is answered about June, not the default month."""
    q = question or ""
    left, right = q, ""
    m = _SPLIT_RE.search(q)
    if m:
        left, right = q[:m.start()], q[m.end():]

    def first(text_: str) -> str | None:
        hit = _PERIOD_RE.search(text_)
        return hit.group(1).strip().lower() if hit else None

    period = first(left)
    compare = first(right) if right else None
    if compare is None and _YOY_RE.search(q):
        compare = "same month last year"
    # 'this month' is already the default; carrying it adds nothing.
    if period in {"this month", "current month"}:
        period = None
    return period, compare


@lru_cache(maxsize=1)
def _lookups() -> tuple[dict, dict, list]:
    with ro_engine().connect() as c:
        products = {r[0]: r[1] for r in c.execute(text("SELECT product_id, product_name FROM products"))}
        regions = {r[0]: r[1] for r in c.execute(text("SELECT region_id, region_name FROM regions"))}
        categories = [r[0] for r in c.execute(text("SELECT DISTINCT category FROM products"))]
    return products, regions, categories


def analyse_question(question: str) -> dict:
    """Classify intent and pull out any entities the user named."""
    products, regions, categories = _lookups()
    q = question or ""
    intent = ("what_if" if _WHATIF.search(q) else
              "action" if _ACTION.search(q) else
              "root_cause" if _WHY.search(q) else "descriptive")

    entities: dict = {}
    for rid, name in regions.items():
        if re.search(rf"\b{name}\b", q, re.I) or re.search(rf"\b{rid}\b", q, re.I):
            entities["region_id"] = rid
            break
    m = re.search(r"\b(P1\d{2})\b", q, re.I)
    if m:
        entities["product_id"] = m.group(1).upper()
    else:
        for pid, name in products.items():
            core = name.split()[-1]
            if re.search(rf"\b{re.escape(name)}\b", q, re.I) or (len(core) > 4 and re.search(rf"\b{core}\b", q, re.I)):
                entities["product_id"] = pid
                break
    for cat in categories:
        if re.search(rf"\b{re.escape(cat)}\b", q, re.I):
            entities["category"] = cat
            break
    m = _PCT.search(q)
    if m:
        entities["pct"] = float(m.group(1))
    period, compare = extract_periods(q)
    if period:
        entities["period_expr"] = period
    if compare:
        entities["compare_expr"] = compare
    if re.search(r"\b(inventory|stock|stockouts?|availability|fill rate)\b", q, re.I):
        entities["topic"] = "inventory"
    elif re.search(r"\b(suppliers?|deliver(y|ies)|lead times?|vendors?|purchase orders?)\b", q, re.I):
        entities["topic"] = "supplier"
    elif re.search(r"\b(marketing|campaigns?|spend|ads?|advertis\w+)\b", q, re.I):
        entities["topic"] = "marketing"
    elif re.search(r"\b(price|pricing|discounts?|discounting)\b", q, re.I):
        entities["topic"] = "pricing"
    elif re.search(r"\b(customers?|churn|segments?)\b", q, re.I):
        entities["topic"] = "customer"
    elif re.search(r"\b(trend|over time|monthly|history)\b", q, re.I):
        entities["topic"] = "trend"
    elif re.search(r"\bregion", q, re.I):
        entities["topic"] = "region"
    elif re.search(r"\bproduct", q, re.I):
        entities["topic"] = "product"
    return {"intent": intent, "entities": entities}


def objective_for(question: str, intent: str, ctx: T.Context) -> str:
    base = f"{ctx.current.label} vs {ctx.previous.label}"
    return {
        "root_cause": f"Explain the {base} movement and identify the dominant driver, with evidence.",
        "action": f"Explain the {base} movement and recommend actions supported by policy.",
        "what_if": f"Quantify the proposed change against the {base} baseline.",
        "descriptive": f"Answer the question directly from the {base} data.",
    }.get(intent, f"Investigate the question over {base}.")


def outline_for(intent: str) -> list[str]:
    if intent in ("root_cause", "action"):
        return [
            "Measure the headline movement and normalise for period length",
            "Locate where it is concentrated (region, then product)",
            "Separate real breaks from noise with an anomaly scan",
            "Test whether it is a supply constraint or a demand shift",
            "Trace the supply chain upstream if stock ran out",
            "Test and rule out the commercial alternatives (marketing, price, customers)",
            "Quantify the impact in rupees and retrieve the governing policy",
        ]
    if intent == "what_if":
        return ["Establish the baseline", "Read the current service level",
                "Simulate the proposed policy change and price the trade-off"]
    return ["Resolve the period", "Pull the specific figures requested"]


# --------------------------------------------------------------------------
@dataclass
class Step:
    tool: str
    args: dict
    rationale: str


def _sig(tool: str, args: dict) -> str:
    return tool + ":" + ",".join(f"{k}={v}" for k, v in sorted(args.items()))


class HeuristicPlanner:
    """An explicit investigation policy - guarded steps, evaluated in order."""

    name = "deterministic"

    def next_step(self, state: dict, ctx: T.Context) -> Step | None:
        f = state.get("facts", {})
        done = set(state.get("executed", []))
        ent = state.get("entities", {})
        intent = state.get("intent", "root_cause")
        region = ent.get("region_id") or f.get("worst_region")
        product = ent.get("product_id") or f.get("worst_product") or f.get("anomaly_top_product")

        for step in self._candidates(intent, ent, f, region, product):
            if _sig(step.tool, step.args) not in done:
                return step
        return None

    # each entry is (guard, Step); the first unexecuted step whose guard holds wins
    def _candidates(self, intent: str, ent: dict, f: dict, region, product) -> list[Step]:
        out: list[Step] = []
        add = out.append

        if intent == "what_if":
            add(Step("get_revenue_summary", {}, "Establish the baseline movement"))
            if product and region:
                add(Step("check_demand_vs_served", {"product_id": product, "region_id": region},
                         "Read the current service level"))
                add(Step("simulate_safety_stock",
                         {"product_id": product, "region_id": region,
                          "uplift_pct": ent.get("pct", 15)},
                         "Price the proposed policy change"))
                add(Step("search_policy", {"query": "safety stock norms for class A products"},
                         "Check the change against policy"))
            return out

        if intent == "descriptive":
            topic = ent.get("topic")
            scope = {k: v for k, v in ent.items() if k in ("region_id", "product_id", "category")}
            if topic == "trend":
                add(Step("get_trend", {"months": 13, **scope}, "Pull the requested series"))
            elif topic == "inventory":
                add(Step("get_inventory_health", scope or {}, "Read the inventory ledger"))
            elif topic == "supplier":
                add(Step("get_supplier_performance",
                         {k: v for k, v in scope.items() if k == "product_id"},
                         "Read purchase-order delivery performance"))
            elif topic == "marketing":
                add(Step("get_marketing_performance", scope, "Read marketing spend and response"))
            elif topic == "pricing":
                add(Step("check_pricing", scope, "Read price and discount movement"))
            elif topic == "customer":
                add(Step("get_customer_metrics",
                         {k: v for k, v in scope.items() if k == "region_id"}, "Read customer activity"))
            elif topic == "product":
                add(Step("get_breakdown", {"dimension": "product", **scope}, "Rank products by movement"))
            elif topic == "region":
                add(Step("get_breakdown", {"dimension": "region"}, "Rank regions by movement"))
            else:
                add(Step("get_revenue_summary", scope, "Measure the headline figure"))
                add(Step("get_breakdown", {"dimension": "region", **scope}, "Show where it sits"))
            return out

        # ---- root cause / action: the full investigation ---------------
        add(Step("get_revenue_summary", {}, "Measure the headline movement first"))
        add(Step("get_trend", {"months": 13}, "Check whether this breaks the trend or continues it"))
        add(Step("get_breakdown", {"dimension": "region"}, "Find which region carries the movement"))
        if region:
            add(Step("detect_anomalies", {"dimension": "product", "region_id": region},
                     f"Separate real breaks from noise inside {region}"))
            add(Step("get_breakdown", {"dimension": "product", "region_id": region},
                     f"Rank products inside {region}"))
        if product:
            add(Step("check_demand_vs_served", {"product_id": product, **({"region_id": region} if region else {})},
                     "Test supply constraint vs demand shift"))
            if f.get("fill_rate_pct") is not None and f["fill_rate_pct"] < 97:
                add(Step("get_inventory_health",
                         {"product_id": product, **({"region_id": region} if region else {})},
                         "Measure the stockout from the daily ledger"))
                add(Step("get_supplier_performance", {"product_id": product},
                         "Trace the shortage upstream to deliveries"))
        if region:
            add(Step("get_marketing_performance", {"region_id": region},
                     "Test the marketing explanation"))
        add(Step("check_pricing", {}, "Test the pricing explanation"))
        if region:
            add(Step("get_customer_metrics", {"region_id": region}, "Test the customer explanation"))
        if product and f.get("unserved_units"):
            add(Step("quantify_impact", {"product_id": product, **({"region_id": region} if region else {})},
                     "Convert unserved demand into rupees"))
        add(Step("search_policy",
                 {"query": "safety stock and low stock alert thresholds for class A products"},
                 "Ground the recommendation in policy"))
        if intent == "action" and product and region:
            add(Step("simulate_safety_stock", {"product_id": product, "region_id": region, "uplift_pct": 15},
                     "Price the recommended change before proposing it"))
        return out


SYSTEM = """You are the supervisor of an autonomous business-intelligence investigation.

You decide the NEXT single step. You never state or compute business numbers
yourself: the tools return validated figures computed in SQL and pandas.

Investigation principles:
- Measure the headline movement before explaining it.
- Follow the money: drill into whichever dimension carries most of the change in
  absolute currency, not the largest percentage on a tiny base.
- Before blaming demand, test supply: unserved demand in the inventory ledger is
  the decisive test.
- If stock ran out, trace it upstream to purchase orders and suppliers.
- Actively test the alternatives you expect to be innocent (pricing, marketing,
  customer mix). An explanation without ruled-out alternatives is not evidence.
- Quantify the impact in currency, and cite policy before recommending anything.
- Do not repeat a tool call with the same arguments. Stop as soon as the evidence
  supports a conclusion; call finish_investigation with a one-line reason.
"""


class LLMPlanner:
    """Model-driven planning, with the heuristic policy as a safety net."""

    def __init__(self) -> None:
        self.llm = get_llm()
        self.fallback = HeuristicPlanner()
        self.name = f"llm:{self.llm.info.provider}:{self.llm.info.model}" if self.llm.available \
            else self.fallback.name

    def next_step(self, state: dict, ctx: T.Context) -> Step | None:
        if not self.llm.available:
            return self.fallback.next_step(state, ctx)
        prompt = self._prompt(state, ctx)
        choice = self.llm.choose_tool(SYSTEM, prompt, T.tool_specs())
        if choice is None:                      # provider failed -> keep going
            self.name = self.fallback.name
            return self.fallback.next_step(state, ctx)
        if choice.get("done"):
            return None
        step = Step(choice["tool"], choice.get("args") or {}, choice.get("rationale") or "")
        if _sig(step.tool, step.args) in set(state.get("executed", [])):
            return self.fallback.next_step(state, ctx)   # no loops
        return step

    def _prompt(self, state: dict, ctx: T.Context) -> str:
        lines = [
            f"Business question: {state['question']}",
            f"Current period: {ctx.current} | Comparison period: {ctx.previous}",
            f"Objective: {state.get('objective', '')}",
            "",
            "Findings so far:" if state.get("findings") else "No findings yet - start the investigation.",
        ]
        for fnd in state.get("findings", []):
            lines.append(f"  {fnd['step']}. [{fnd['tool']}] {fnd['summary']}")
        if state.get("facts"):
            known = {k: v for k, v in state["facts"].items() if v is not None}
            lines += ["", "Known figures: " + ", ".join(f"{k}={v}" for k, v in list(known.items())[:24])]
        lines += ["", f"Steps used: {state.get('steps_used', 0)}. Choose the next tool, or "
                      "finish_investigation if the evidence is sufficient."]
        return "\n".join(lines)


def get_planner() -> LLMPlanner:
    return LLMPlanner()
