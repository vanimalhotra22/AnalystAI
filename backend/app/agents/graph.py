"""The investigation graph (LangGraph).

    START -> understand -> investigate --(more evidence needed)--> investigate
                                        \\--(enough)--> validate -> conclude -> narrate -> END

`investigate` performs exactly one tool call per visit and loops back through a
conditional edge, so the investigation length is decided at run time by the
planner and the evidence -- not by a fixed pipeline.  Every node emits events,
which the API streams to the UI as the run unfolds.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from app.agents import report as R
from app.agents import scoring, tools as T
from app.agents.llm import get_llm
from app.agents.planner import analyse_question, get_planner, objective_for, outline_for
from app.agents.state import InvestigationState, new_state
from app.config import settings

Emit = Callable[[dict], None]


def _emit(config: dict | None, kind: str, message: str = "", **payload: Any) -> None:
    fn: Emit | None = (config or {}).get("configurable", {}).get("emit")
    if fn:
        fn({"type": kind, "message": message, "ts": time.time(), **payload})


def _ctx(state: InvestigationState) -> T.Context:
    return T.default_context(state.get("period_expr"), state.get("compare_expr"),
                             state.get("question", ""))


# ------------------------------------------------------------------- nodes
def understand(state: InvestigationState, config=None) -> dict:
    parsed = analyse_question(state["question"])
    intent, entities = parsed["intent"], parsed["entities"]
    # An explicit API argument wins; otherwise use the period named in the question.
    state = {**state,
             "period_expr": state.get("period_expr") or entities.get("period_expr"),
             "compare_expr": state.get("compare_expr") or entities.get("compare_expr")}
    ctx = _ctx(state)
    objective = objective_for(state["question"], intent, ctx)
    plan = outline_for(intent)
    planner = get_planner()

    _emit(config, "status", "Understanding the business question")
    _emit(config, "understanding",
          f"Intent: {intent.replace('_', ' ')}. Comparing {ctx.current.label} with {ctx.previous.label}.",
          intent=intent, entities=entities,
          current_period=ctx.current.as_dict(), comparison_period=ctx.previous.as_dict(),
          objective=objective, planner=planner.name, llm=get_llm().describe())
    _emit(config, "plan", "Investigation plan drafted", plan=plan)
    return {"intent": intent, "entities": entities, "objective": objective, "plan": plan,
            "period_expr": state.get("period_expr"), "compare_expr": state.get("compare_expr"),
            "current_period": ctx.current.as_dict(), "comparison_period": ctx.previous.as_dict(),
            "planner": planner.name, "llm": get_llm().describe()}


def investigate(state: InvestigationState, config=None) -> dict:
    ctx = _ctx(state)
    planner = get_planner()
    step_no = state.get("steps_used", 0) + 1

    step = planner.next_step(dict(state), ctx)
    if step is None:
        _emit(config, "status", "Evidence is sufficient - moving to validation")
        return {"steps_used": state.get("steps_used", 0), "planner": planner.name}

    _emit(config, "tool_start", step.rationale or f"Running {step.tool}",
          step=step_no, tool=step.tool, args=step.args)
    started = time.perf_counter()
    result = T.call_tool(step.tool, step.args, ctx)
    elapsed = int((time.perf_counter() - started) * 1000)

    finding = {"step": step_no, "tool": step.tool, "args": step.args,
               "summary": result.get("summary", ""), "data": result.get("data", {}),
               "facts": result.get("facts", {}), "error": bool(result.get("error"))}
    _emit(config, "finding", result.get("summary", ""), step=step_no, tool=step.tool,
          args=step.args, facts=result.get("facts", {}), elapsed_ms=elapsed,
          error=bool(result.get("error")))

    out: dict = {"findings": [finding], "facts": result.get("facts", {}) or {},
                 "executed": [step.tool + ":" + ",".join(f"{k}={v}" for k, v in sorted(step.args.items()))],
                 "steps_used": step_no, "planner": planner.name}
    if result.get("error"):
        out["warnings"] = [f"step {step_no} ({step.tool}) failed: {result.get('summary')}"]
    return out


def should_continue(state: InvestigationState) -> str:
    if state.get("steps_used", 0) >= settings.max_investigation_steps:
        return "validate"
    ctx = _ctx(state)
    nxt = get_planner().next_step(dict(state), ctx)
    return "investigate" if nxt else "validate"


def validate(state: InvestigationState, config=None) -> dict:
    _emit(config, "status", "Validating evidence and testing alternative explanations")
    facts = state.get("facts", {})
    hypotheses = scoring.evaluate(facts)
    chain = scoring.causal_chain(facts, hypotheses)
    confidence, reasons = scoring.overall_confidence(hypotheses, facts)

    for h in hypotheses:
        _emit(config, "hypothesis",
              f"{h['label']}: {h['status'].replace('_', ' ')} (score {h['score']})",
              key=h["key"], status=h["status"], score=h["score"], evidence=h["evidence"],
              note=h["note"])
    _emit(config, "causal_chain", "Mechanism assembled from measured links", chain=chain)
    return {"hypotheses": hypotheses, "causal_chain": chain, "confidence": confidence,
            "confidence_reasons": reasons,
            "evidence": [e for h in hypotheses if h["status"] in ("supported", "partial")
                         for e in h["evidence"]]}


def conclude(state: InvestigationState, config=None) -> dict:
    facts = state.get("facts", {})
    hypotheses = state.get("hypotheses", [])
    supported = [h for h in hypotheses if h["status"] == "supported"]
    primary = max(supported, key=lambda h: h["score"]) if supported else None
    upstream = next((h for h in supported if h.get("upstream_of") == (primary or {}).get("key")), None)

    root = None
    if primary:
        root = {
            "key": primary["key"], "label": primary["label"], "score": primary["score"],
            "evidence": primary["evidence"],
            "originating_cause": upstream["label"] if upstream else None,
            "statement": _root_statement(primary, upstream, facts),
        }
        _emit(config, "root_cause", root["statement"], **root)
    else:
        _emit(config, "root_cause", "No single explanation reached the evidence threshold; "
                                    "reporting the ranked candidates instead.")

    recs = R.build_recommendations(facts, hypotheses, state.get("findings", []))
    for r in recs:
        _emit(config, "recommendation", r["action"], priority=r["priority"], why=r["why"],
              policy=(r.get("policy") or {}).get("section"),
              approval_required=r["approval_required"])
    return {"root_cause": root, "recommendations": recs}


def _root_statement(primary: dict, upstream: dict | None, facts: dict) -> str:
    product = facts.get("worst_product_label") or facts.get("worst_product") or "the affected line"
    region = facts.get("worst_region_label") or facts.get("worst_region") or "the affected region"
    base = f"{primary['label']}: {product} in {region}"
    if facts.get("stockout_days"):
        base += (f" was out of stock for {facts['stockout_days']} day(s)"
                 + (f" ({facts.get('stockout_window')})" if facts.get("stockout_window") else ""))
    if upstream:
        base += f", originating from {upstream['label'].lower()}"
        if facts.get("worst_po_delay_days"):
            base += (f" ({facts.get('worst_po_supplier')} delivered {facts['worst_po_delay_days']} days "
                     f"late on {facts.get('worst_po_id')})")
    return base + "."


def narrate(state: InvestigationState, config=None) -> dict:
    _emit(config, "status", "Writing the executive summary")
    text, source = R.narrate(dict(state))
    merged = {**dict(state), "narrative": text, "narrative_source": source}
    report = R.build_report(merged)
    _emit(config, "narrative", text, source=source)
    _emit(config, "report", "Investigation complete", report=report)
    return {"narrative": text, "narrative_source": source, "report": report}


# ------------------------------------------------------------------- graph
def build_graph():
    g = StateGraph(InvestigationState)
    g.add_node("understand", understand)
    g.add_node("investigate", investigate)
    g.add_node("validate", validate)
    g.add_node("conclude", conclude)
    g.add_node("narrate", narrate)

    g.add_edge(START, "understand")
    g.add_edge("understand", "investigate")
    g.add_conditional_edges("investigate", should_continue,
                            {"investigate": "investigate", "validate": "validate"})
    g.add_edge("validate", "conclude")
    g.add_edge("conclude", "narrate")
    g.add_edge("narrate", END)
    return g.compile()


_GRAPH = None


def graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_investigation(question: str, period: str | None = None, compare_to: str | None = None,
                      emit: Emit | None = None, run_id: str | None = None) -> dict:
    run_id = run_id or uuid.uuid4().hex[:12]
    state = new_state(question, period, compare_to, run_id)
    config = {"configurable": {"emit": emit},
              "recursion_limit": settings.max_investigation_steps * 3 + 15}
    if emit:
        emit({"type": "run_started", "message": "Investigation started", "run_id": run_id,
              "question": question, "ts": time.time()})
    final = graph().invoke(state, config=config)
    return final.get("report") or R.build_report(dict(final))
