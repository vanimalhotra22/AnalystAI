"""Investigation state.

One dict travels through the graph and accumulates everything the run has
learned.  It is the audit trail: question -> plan -> tool calls -> findings ->
facts -> hypotheses -> root cause -> recommendations -> report.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict


def _extend(left: list, right: list) -> list:
    return (left or []) + (right or [])


def _merge(left: dict, right: dict) -> dict:
    return {**(left or {}), **(right or {})}


class Finding(TypedDict, total=False):
    step: int
    tool: str
    args: dict
    summary: str
    data: dict
    facts: dict
    error: bool


class InvestigationState(TypedDict, total=False):
    # inputs
    question: str
    period_expr: str | None
    compare_expr: str | None
    run_id: str

    # understanding
    objective: str
    intent: Literal["root_cause", "descriptive", "action", "what_if", "unknown"]
    entities: dict
    current_period: dict
    comparison_period: dict
    plan: list[str]

    # investigation
    findings: Annotated[list[Finding], _extend]
    facts: Annotated[dict, _merge]
    executed: Annotated[list[str], _extend]
    steps_used: int

    # conclusions
    hypotheses: list[dict]
    root_cause: dict
    causal_chain: list[dict]
    evidence: list[dict]
    attribution: dict
    recommendations: list[dict]
    confidence: float
    confidence_reasons: list[str]
    narrative: str
    narrative_source: str
    report: dict

    # meta
    planner: str
    llm: dict
    warnings: Annotated[list[str], _extend]


def new_state(question: str, period: str | None = None, compare_to: str | None = None,
              run_id: str = "") -> InvestigationState:
    return {
        "question": question, "period_expr": period, "compare_expr": compare_to,
        "run_id": run_id, "findings": [], "facts": {}, "executed": [], "steps_used": 0,
        "hypotheses": [], "evidence": [], "recommendations": [], "warnings": [],
        "intent": "unknown", "entities": {}, "plan": [],
    }


def key_numbers(state: InvestigationState) -> dict[str, Any]:
    """The handful of scalars the UI header shows."""
    f = state.get("facts", {})
    return {
        "revenue_pct_change": f.get("revenue_pct_change"),
        "revenue_per_day_pct_change": f.get("revenue_per_day_pct_change"),
        "revenue_delta": f.get("revenue_delta"),
        "worst_region": f.get("worst_region_label") or f.get("worst_region"),
        "worst_product": f.get("worst_product_label") or f.get("worst_product"),
        "stockout_days": f.get("stockout_days"),
        "fill_rate_pct": f.get("fill_rate_pct"),
        "lost_revenue_display": f.get("lost_revenue_display"),
    }
