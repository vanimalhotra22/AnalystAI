"""The agent's action space.

Each tool is a thin, typed wrapper around a deterministic analytics function.
A tool returns three things:

  summary  one sentence of plain English *with the real numbers in it* -- this is
           what streams into the activity feed, so the feed is trustworthy even
           if the model narrates badly afterwards;
  data     the structured result (charts and the report render from this);
  facts    a flat, namespaced dict of scalars that the hypothesis scorer reads.

The model chooses tools and arguments.  It never produces the numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.analytics import anomaly as A
from app.analytics import impact as I
from app.analytics import metrics as M
from app.analytics.periods import Period, resolve_comparison, resolve_period
from app.agents import knowledge as K
from app.agents.sql_tool import SQLGuardError, run_sql

INR = M.fmt_inr


@dataclass
class Context:
    current: Period
    previous: Period
    question: str = ""


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., dict]
    cost_hint: str = "fast"

    def spec(self) -> dict:
        """JSON-Schema tool definition handed to the model (the internal
        'required' flag on a property is lifted into the schema's required list)."""
        props = {k: {pk: pv for pk, pv in v.items() if pk != "required"}
                 for k, v in self.parameters.items()}
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": props,
                                 "required": [k for k, v in self.parameters.items()
                                              if v.get("required")]}}


REGION_ENUM = ["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"]


def _pp(v: float | None, suffix: str = "%") -> str:
    return "n/a" if v is None else f"{v:+.1f}{suffix}"


# --------------------------------------------------------------------- tools
def t_revenue_summary(ctx: Context, **kw) -> dict:
    filters = {k: v for k, v in kw.items() if k in ("region_id", "product_id", "category")}
    res = M.revenue_summary(ctx.current, ctx.previous, filters)
    ch = res.get("change", {})
    scope = " / ".join(f"{k}={v}" for k, v in filters.items()) or "company-wide"
    summary = (f"{scope}: revenue {INR(res['current']['revenue'])} in {ctx.current.label} vs "
               f"{INR(res['previous']['revenue'])} in {ctx.previous.label} "
               f"({_pp(ch.get('revenue_pct'))}, {_pp(ch.get('revenue_per_day_pct'))} per day; "
               f"units {_pp(ch.get('units_pct'))}, orders {_pp(ch.get('orders_pct'))}).")
    facts = {"revenue_pct_change": ch.get("revenue_pct"),
             "revenue_per_day_pct_change": ch.get("revenue_per_day_pct"),
             "revenue_delta": ch.get("revenue_delta"),
             "units_pct_change": ch.get("units_pct"),
             "orders_pct_change": ch.get("orders_pct"),
             "aov_pct_change": ch.get("aov_pct")} if not filters else {}
    return {"summary": summary, "data": res, "facts": facts}


def t_breakdown(ctx: Context, dimension: str = "region", top_n: int = 8, **kw) -> dict:
    filters = {k: v for k, v in kw.items() if k in ("region_id", "product_id", "category", "segment")}
    res = M.breakdown(dimension, ctx.current, ctx.previous, filters, top_n=top_n)
    rows = res["rows"]
    if not rows:
        return {"summary": f"No {dimension} data for the requested scope.", "data": res, "facts": {}}
    w = rows[0]
    scope = " / ".join(f"{k}={v}" for k, v in filters.items()) or "company-wide"
    summary = (f"By {dimension} ({scope}): {w['label']} moved {INR(w['delta'])} "
               f"({_pp(w['pct_change'])}), which is {w['share_of_decline_pct']:.0f}% of the total decline; "
               f"next: " + ", ".join(f"{r['label']} {_pp(r['pct_change'])}" for r in rows[1:3]) + ".")
    facts = {f"worst_{dimension}": w["key"], f"worst_{dimension}_label": w["label"],
             f"worst_{dimension}_delta": w["delta"], f"worst_{dimension}_pct": w["pct_change"],
             f"worst_{dimension}_share_of_decline": w["share_of_decline_pct"]}
    if filters.get("region_id"):
        facts["breakdown_scope_region"] = filters["region_id"]
    return {"summary": summary, "data": res, "facts": facts}


def t_trend(ctx: Context, months: int = 13, **kw) -> dict:
    filters = {k: v for k, v in kw.items() if k in ("region_id", "product_id", "category")}
    res = M.trend(ctx.current, months=months, filters=filters)
    pts = res["points"]
    tail = ", ".join(f"{p['period']} {INR(p['revenue'])}" for p in pts[-4:])
    return {"summary": f"Revenue trend ({len(pts)} months): {tail}.", "data": res, "facts": {}}


def t_detect_anomalies(ctx: Context, dimension: str = "product", **kw) -> dict:
    filters = {k: v for k, v in kw.items() if k in ("region_id", "category")}
    res = A.detect_anomalies(dimension, ctx.current, filters)
    flagged = [r for r in res["flagged"] if r["pct_change"] < 0] or res["flagged"]
    if flagged:
        top = flagged[0]
        summary = (f"Anomaly scan over {dimension} ({res['method']}, {res['history_months']} months of "
                   f"history): {len(res['flagged'])} outlier(s). Strongest: {top['label']} at "
                   f"{_pp(top['pct_change'])} vs a typical {INR(top['expected_revenue_median'])} "
                   f"(z={top['z_score']}, score={top['anomaly_score']}).")
        facts = {f"anomaly_top_{dimension}": top["key"], f"anomaly_top_{dimension}_label": top["label"],
                 f"anomaly_top_{dimension}_z": top["z_score"],
                 f"anomaly_top_{dimension}_score": top["anomaly_score"]}
    else:
        summary = f"Anomaly scan over {dimension}: nothing breaks pattern beyond normal variation."
        facts = {f"anomaly_top_{dimension}": None}
    return {"summary": summary, "data": res, "facts": facts}


def t_inventory_health(ctx: Context, product_id: str | None = None,
                       region_id: str | None = None, **_) -> dict:
    res = M.inventory_health(ctx.current, product_id, region_id)
    if not res.get("by_product_region"):
        return {"summary": "No inventory movement found for that scope.", "data": res, "facts": {}}
    scope = f"{product_id or 'all products'}{' / ' + region_id if region_id else ''}"
    win = res["stockout_window"]
    window_txt = f" (longest run {res['longest_stockout_streak_days']}d: {win['start']} to {win['end']})" \
        if res["longest_stockout_streak_days"] else ""
    summary = (f"Inventory {scope} in {ctx.current.label}: {res['stockout_days']} stockout day(s)"
               f"{window_txt}, {res['units_lost']} units of demand unserved "
               f"(~{INR(res['lost_revenue_estimate'])} at list).")
    facts = {"stockout_days": res["stockout_days"],
             "stockout_streak_days": res["longest_stockout_streak_days"],
             "stockout_window": f"{win['start']} to {win['end']}" if win["start"] else None,
             "units_lost": res["units_lost"],
             "inventory_scope": scope}
    return {"summary": summary, "data": res, "facts": facts}


def t_demand_vs_served(ctx: Context, product_id: str, region_id: str | None = None, **_) -> dict:
    res = A.demand_vs_served(ctx.current, product_id, region_id)
    if not res:
        return {"summary": "No inventory ledger rows for that scope.", "data": {}, "facts": {}}
    summary = (f"{product_id}{'/' + region_id if region_id else ''}: demand was "
               f"{res['true_demand_units']} units, {res['served_units']} served, "
               f"{res['unserved_units']} unserved - fill rate {res['fill_rate_pct']}% "
               f"({res['interpretation']}).")
    return {"summary": summary, "data": res,
            "facts": {"fill_rate_pct": res["fill_rate_pct"],
                      "unserved_units": res["unserved_units"],
                      "supply_side": res["unserved_units"] > 0}}


def t_supplier_performance(ctx: Context, supplier_id: str | None = None,
                           product_id: str | None = None, **_) -> dict:
    res = M.supplier_performance(ctx.current, supplier_id, product_id)
    if not res.get("purchase_orders"):
        return {"summary": "No purchase orders in the window.", "data": res, "facts": {}}
    worst = res["worst_purchase_orders"][0]
    summary = (f"Supplier delivery in {ctx.current.label}: average delay "
               f"{res['avg_delay_days_in_period']} days vs {res['avg_delay_days_baseline']} days in the "
               f"preceding baseline. Worst: {worst['po_id']} ({worst['supplier_name']}, {worst['product_id']} "
               f"to {worst['warehouse_id']}) promised {worst['promised_date']}, received "
               f"{worst['received_date']} - {worst['delay_days']} days late.")
    facts = {"supplier_avg_delay_days": res["avg_delay_days_in_period"],
             "supplier_baseline_delay_days": res["avg_delay_days_baseline"],
             "worst_po_delay_days": worst["delay_days"], "worst_po_id": worst["po_id"],
             "worst_po_supplier": worst["supplier_name"]}
    return {"summary": summary, "data": res, "facts": facts}


def t_marketing_performance(ctx: Context, **kw) -> dict:
    filters = {k: v for k, v in kw.items() if k in ("region_id", "product_id", "category")}
    res = M.marketing_performance(ctx.current, ctx.previous, filters)
    scope = " / ".join(f"{k}={v}" for k, v in filters.items()) or "company-wide"
    summary = (f"Marketing {scope}: spend {INR(res['spend_current'])} vs {INR(res['spend_previous'])} "
               f"({_pp(res['spend_pct_change'])}), clicks {_pp(res['clicks_pct_change'])}, "
               f"conversions {_pp(res['conversions_pct_change'])}.")
    key = "marketing_spend_pct_change" + ("_scoped" if filters else "")
    return {"summary": summary, "data": res,
            "facts": {key: res["spend_pct_change"], "marketing_scope": scope}}


def t_pricing_check(ctx: Context, **kw) -> dict:
    filters = {k: v for k, v in kw.items() if k in ("region_id", "product_id", "category")}
    res = M.pricing_check(ctx.current, ctx.previous, filters)
    if not res:
        return {"summary": "No sales rows for that scope.", "data": {}, "facts": {}}
    summary = (f"Pricing check: average discount {res['current']['avg_discount_pct']}% vs "
               f"{res['previous']['avg_discount_pct']}% "
               f"({res['discount_pct_point_change']:+.2f} pts), realised price per unit "
               f"{_pp(res['realised_price_pct_change'])}.")
    return {"summary": summary, "data": res,
            "facts": {"discount_pp_change": res["discount_pct_point_change"],
                      "realised_price_pct_change": res["realised_price_pct_change"]}}


def t_customer_metrics(ctx: Context, **kw) -> dict:
    filters = {k: v for k, v in kw.items() if k in ("region_id", "segment", "category")}
    res = M.customer_metrics(ctx.current, ctx.previous, filters)
    if not res:
        return {"summary": "No customer activity for that scope.", "data": {}, "facts": {}}
    summary = (f"Customers: {res['active_customers_current']} active vs "
               f"{res['active_customers_previous']} ({_pp(res['active_customers_pct_change'])}), "
               f"revenue per customer {INR(res['revenue_per_customer_current'])} vs "
               f"{INR(res['revenue_per_customer_previous'])}.")
    return {"summary": summary, "data": res,
            "facts": {"active_customers_pct_change": res["active_customers_pct_change"]}}


def t_quantify_impact(ctx: Context, product_id: str, region_id: str | None = None, **_) -> dict:
    res = I.quantify_stockout_impact(ctx.current, product_id, region_id)
    summary = (f"Quantified impact for {product_id}{'/' + region_id if region_id else ''}: "
               f"{res['unserved_units']} unserved units x {INR(res['realised_price_per_unit'])} realised "
               f"price = {res['lost_revenue_display']} of revenue not captured "
               f"({res['stockout_days']} stockout days).")
    return {"summary": summary, "data": res,
            "facts": {"lost_revenue": res["lost_revenue"],
                      "lost_revenue_display": res["lost_revenue_display"]}}


def t_simulate_safety_stock(ctx: Context, product_id: str, region_id: str,
                            uplift_pct: float = 15.0, **_) -> dict:
    res = I.simulate_safety_stock(product_id, region_id, uplift_pct, trials=1500)
    if res.get("error"):
        return {"summary": res["error"], "data": res, "facts": {}}
    cur, up, ec = res["current_policy"], res["uplifted_policy"], res["economics"]
    summary = (f"What-if (+{uplift_pct:.0f}% safety stock on {product_id}/{region_id}): stockout risk "
               f"{cur['stockout_probability_pct']}% -> {up['stockout_probability_pct']}%, protected revenue "
               f"{ec['protected_revenue_display']} against {ec['additional_holding_cost_display']} of extra "
               f"holding cost - net {ec['net_benefit_display']} per 90 days.")
    return {"summary": summary, "data": res,
            "facts": {"whatif_net_benefit": ec["net_benefit"],
                      "whatif_net_benefit_display": ec["net_benefit_display"]}}


def t_search_policy(ctx: Context, query: str, **_) -> dict:
    hits = K.search(query, k=3)
    if not hits:
        return {"summary": f"No policy text matched '{query}'.", "data": {"results": []}, "facts": {}}
    top = hits[0]
    summary = (f"Policy lookup '{query}': {top['policy']} - {top['section']} "
               f"(relevance {top['relevance']}), plus {len(hits) - 1} related section(s).")
    return {"summary": summary, "data": {"results": hits},
            "facts": {"policy_citation": f"{top['policy']} / {top['section']}"}}


def t_run_sql(ctx: Context, sql: str, **_) -> dict:
    try:
        res = run_sql(sql)
    except SQLGuardError as e:
        return {"summary": f"SQL rejected by the guard: {e}", "data": {"error": str(e), "sql": sql},
                "facts": {}, "error": True}
    preview = res.rows[:5]
    return {"summary": f"Ad-hoc query returned {res.row_count} row(s) in {res.elapsed_ms} ms.",
            "data": {"sql": res.sql, "columns": res.columns, "rows": preview,
                     "row_count": res.row_count, "truncated": res.truncated},
            "facts": {}}


# ------------------------------------------------------------------ registry
def _p(t: str, desc: str, required: bool = False, enum: list | None = None, default=None) -> dict:
    d: dict[str, Any] = {"type": t, "description": desc}
    if enum:
        d["enum"] = enum
    if required:
        d["required"] = True
    if default is not None:
        d["default"] = default
    return d


REGION_P = _p("string", "Restrict to one region.", enum=REGION_ENUM)
PRODUCT_P = _p("string", "Restrict to one product id, e.g. P103.")
CATEGORY_P = _p("string", "Restrict to one product category.")

TOOLS: dict[str, Tool] = {}


def _reg(tool: Tool) -> None:
    TOOLS[tool.name] = tool


_reg(Tool("get_revenue_summary",
          "Headline revenue, units, orders and AOV for the period vs the comparison period. "
          "Start here for any 'what happened' question.",
          {"region_id": REGION_P, "product_id": PRODUCT_P, "category": CATEGORY_P},
          t_revenue_summary))

_reg(Tool("get_breakdown",
          "Revenue by region / product / category / channel / segment for both periods, with each "
          "member's share of the total change. Use it to find where a movement is concentrated. "
          "Filter by region_id to drill inside a region.",
          {"dimension": _p("string", "Dimension to split by.", required=True,
                           enum=["region", "product", "category", "channel", "segment", "supplier"]),
           "region_id": REGION_P, "product_id": PRODUCT_P, "category": CATEGORY_P,
           "top_n": _p("integer", "How many rows to return.", default=8)},
          t_breakdown))

_reg(Tool("get_trend",
          "Monthly revenue series ending with the current period, to see whether a movement is a "
          "break in trend or a continuation.",
          {"months": _p("integer", "How many months.", default=13), "region_id": REGION_P,
           "product_id": PRODUCT_P, "category": CATEGORY_P},
          t_trend))

_reg(Tool("detect_anomalies",
          "Statistical outlier scan (robust z-score + IsolationForest) over a dimension, against each "
          "entity's own 12-month history. Use it to separate a real break from normal noise.",
          {"dimension": _p("string", "Dimension to scan.", required=True,
                           enum=["product", "region", "category", "channel", "segment"]),
           "region_id": REGION_P, "category": CATEGORY_P},
          t_detect_anomalies))

_reg(Tool("get_inventory_health",
          "Stockout days, longest stockout run and unserved units from the daily inventory ledger.",
          {"product_id": PRODUCT_P, "region_id": REGION_P},
          t_inventory_health))

_reg(Tool("check_demand_vs_served",
          "Compare true demand (served + unserved) with what stock could serve, giving a fill rate. "
          "This is the test that separates a supply problem from a demand problem.",
          {"product_id": _p("string", "Product id, e.g. P103.", required=True), "region_id": REGION_P},
          t_demand_vs_served))

_reg(Tool("get_supplier_performance",
          "Purchase-order delivery performance: promised vs received dates, delay days in the period "
          "against the preceding baseline. Use it to test whether a stockout was caused upstream.",
          {"supplier_id": _p("string", "Supplier id, e.g. SUP03."), "product_id": PRODUCT_P},
          t_supplier_performance))

_reg(Tool("get_marketing_performance",
          "Marketing spend, clicks and conversions for both periods, optionally scoped to a region, "
          "product or category. Use it to test a demand-side explanation.",
          {"region_id": REGION_P, "product_id": PRODUCT_P, "category": CATEGORY_P},
          t_marketing_performance))

_reg(Tool("check_pricing",
          "Average discount and realised price per unit across both periods, to test (or rule out) a "
          "pricing or discounting explanation.",
          {"region_id": REGION_P, "product_id": PRODUCT_P, "category": CATEGORY_P},
          t_pricing_check))

_reg(Tool("get_customer_metrics",
          "Active customers, returning customers, revenue per customer and segment mix, to test a "
          "customer-churn explanation.",
          {"region_id": REGION_P, "segment": _p("string", "Customer segment.")},
          t_customer_metrics))

_reg(Tool("quantify_impact",
          "Convert unserved units into rupees using the realised price for the same product, region "
          "and period. Call this once the driver is identified.",
          {"product_id": _p("string", "Product id.", required=True), "region_id": REGION_P},
          t_quantify_impact))

_reg(Tool("simulate_safety_stock",
          "Monte-Carlo what-if: stockout risk and net rupee benefit of raising safety stock, using the "
          "product's own demand history and the supplier's own lead-time distribution.",
          {"product_id": _p("string", "Product id.", required=True),
           "region_id": _p("string", "Region id.", required=True, enum=REGION_ENUM),
           "uplift_pct": _p("number", "Safety-stock uplift in percent.", default=15)},
          t_simulate_safety_stock, cost_hint="slow"))

_reg(Tool("search_policy",
          "Retrieve the relevant clause from internal policy documents (inventory, supplier, pricing, "
          "marketing, reporting). Recommendations must cite policy rather than invent thresholds.",
          {"query": _p("string", "What to look up.", required=True)},
          t_search_policy))

_reg(Tool("run_sql",
          "Escape hatch: run one read-only SELECT against the analytics schema. Only use it when no "
          "other tool can answer the question; the query is validated and row-capped.",
          {"sql": _p("string", "A single SELECT statement.", required=True)},
          t_run_sql))


def tool_specs() -> list[dict]:
    return [t.spec() for t in TOOLS.values()]


def call_tool(name: str, args: dict, ctx: Context) -> dict:
    tool = TOOLS.get(name)
    if tool is None:
        return {"summary": f"Unknown tool '{name}'.", "data": {}, "facts": {}, "error": True}
    clean = {k: v for k, v in (args or {}).items() if v not in (None, "", "all")}
    try:
        out = tool.fn(ctx, **clean)
    except TypeError as e:
        return {"summary": f"Invalid arguments for {name}: {e}", "data": {}, "facts": {}, "error": True}
    except Exception as e:  # analytics failures must not kill the investigation
        return {"summary": f"{name} failed: {type(e).__name__}: {e}", "data": {}, "facts": {}, "error": True}
    out.setdefault("facts", {})
    out.setdefault("data", {})
    return {"tool": name, "args": clean, **out}


def default_context(period: str | None = None, compare_to: str | None = None,
                    question: str = "") -> Context:
    cur = resolve_period(period)
    return Context(current=cur, previous=resolve_comparison(cur, compare_to), question=question)
