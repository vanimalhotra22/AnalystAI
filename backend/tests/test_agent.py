"""End-to-end agent behaviour: the investigation must reach the right conclusion,
show its evidence, and stay inside its budget."""
from __future__ import annotations

from app.agents.graph import run_investigation
from app.agents.planner import analyse_question, extract_periods
from app.agents.tools import TOOLS, call_tool, default_context, tool_specs
from app.config import settings

QUESTION = "Revenue decreased this month. Find out why and recommend what we should do."


def test_question_understanding():
    assert analyse_question("Why did revenue decline?")["intent"] == "root_cause"
    assert analyse_question("What should we do about it?")["intent"] == "action"
    assert analyse_question("What if we increase safety stock by 15%?")["intent"] == "what_if"
    assert analyse_question("Which region performed worst?")["intent"] == "descriptive"
    ents = analyse_question("Why did P103 fall in North?")["entities"]
    assert ents["product_id"] == "P103" and ents["region_id"] == "NORTH"


def test_period_extraction_from_text():
    assert extract_periods("revenue in June 2026") == ("june 2026", None)
    assert extract_periods("2026-07 versus 2026-06") == ("2026-07", "2026-06")
    assert extract_periods("July 2026 vs the same month last year")[1] == "same month last year"


def test_every_tool_declares_a_usable_schema():
    for spec in tool_specs():
        assert spec["name"] and spec["description"]
        props = spec["input_schema"]["properties"]
        assert all("required" not in p for p in props.values()), "internal flag leaked into schema"
        for name in spec["input_schema"]["required"]:
            assert name in props


def test_unknown_tool_and_bad_arguments_do_not_raise():
    ctx = default_context()
    assert call_tool("no_such_tool", {}, ctx)["error"] is True
    assert call_tool("get_breakdown", {"dimension": "colour"}, ctx)["error"] is True


def test_full_investigation_finds_the_planted_root_cause():
    report = run_investigation(QUESTION)

    assert report["root_cause"]["key"] == "inventory_stockout"
    assert report["root_cause"]["originating_cause"], "supply chain link not traced upstream"
    assert report["headline"]["primary_region"] == "North"
    assert report["headline"]["primary_product"].startswith("SmartAir Purifier")
    assert report["steps_used"] <= settings.max_investigation_steps + 1

    # alternatives must be tested, not ignored
    statuses = {h["key"]: h["status"] for h in report["hypotheses"]}
    assert statuses["pricing_discounting"] == "ruled_out"
    assert statuses["customer_churn"] == "ruled_out"
    assert statuses["supplier_delay"] == "supported"

    # every supported hypothesis carries evidence with a named source
    for h in report["hypotheses"]:
        if h["status"] in ("supported", "partial"):
            assert h["evidence"], f"{h['key']} has no evidence"
            assert all(e["source"] for e in h["evidence"])

    # the mechanism is a chain, not a single assertion
    steps = [c["step"] for c in report["causal_chain"]]
    assert steps.index("Stock ran out") < steps.index("Company revenue fell")

    # recommendations are actionable, cited and gated on a human
    assert len(report["recommendations"]) >= 3
    assert any(r["approval_required"] for r in report["recommendations"])
    assert any(r.get("policy") for r in report["recommendations"])

    assert 0 < report["confidence"] <= 0.92


def test_investigation_is_reproducible():
    a = run_investigation("Why did revenue decline this month?")
    b = run_investigation("Why did revenue decline this month?")
    assert a["headline"] == b["headline"]
    assert [f["tool"] for f in a["findings"]] == [f["tool"] for f in b["findings"]]


def test_narrative_contains_no_invented_headline_number():
    report = run_investigation("Why did revenue decline this month?")
    pct = report["headline"]["revenue_change_pct"]
    assert str(abs(pct)) in report["narrative"], "narrative must quote the validated figure"
