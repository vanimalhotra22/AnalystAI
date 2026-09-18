"""Evaluation runner.

    python -m app.eval.runner            # whole suite
    python -m app.eval.runner --id Q01   # one question
    python -m app.eval.runner --json docs/eval_report.json

Checks four things per question:
  understanding  was the intent classified correctly
  tool selection did it reach for the right evidence
  metric truth   do the agent's headline numbers match an INDEPENDENT SQL query
  conclusion     right root cause, and the alternatives it should have dismissed
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from sqlalchemy import text

from app.agents.graph import run_investigation
from app.analytics.periods import resolve_comparison, resolve_period
from app.config import ROOT
from app.db.session import ro_engine
from app.eval.suite import SUITE

TOL = 0.05  # percentage points of tolerance against the independent query


def ground_truth(period: str | None, compare_to: str | None) -> dict:
    """Compute the headline movement with a separate, hand-written query so the
    agent's figure is checked against something it did not produce."""
    cur = resolve_period(period)
    prev = resolve_comparison(cur, compare_to)
    sql = text("""
        SELECT
          SUM(CASE WHEN date BETWEEN :cs AND :ce THEN revenue ELSE 0 END) AS cur_rev,
          SUM(CASE WHEN date BETWEEN :ps AND :pe THEN revenue ELSE 0 END) AS prev_rev
        FROM sales WHERE date BETWEEN :ps AND :ce
    """)
    with ro_engine().connect() as c:
        cur_rev, prev_rev = c.execute(sql, {"cs": cur.start, "ce": cur.end,
                                            "ps": prev.start, "pe": prev.end}).one()
    pct = (cur_rev - prev_rev) / prev_rev * 100 if prev_rev else None
    return {"current_revenue": float(cur_rev), "previous_revenue": float(prev_rev),
            "revenue_pct_change": round(pct, 2) if pct is not None else None,
            "period": cur.label, "comparison": prev.label}


def check(case: dict, report: dict) -> dict:
    exp = case["expect"]
    facts = {}
    for f in report.get("findings", []):
        facts.update(f.get("facts") or {})
    tools = [f["tool"] for f in report.get("findings", [])]
    results: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, bool(ok), detail))

    if "intent" in exp:
        add("intent", report.get("intent") == exp["intent"],
            f"got {report.get('intent')}, expected {exp['intent']}")
    for t in exp.get("tools_all", []):
        add(f"tool:{t}", t in tools, "not called")
    if exp.get("tools_any"):
        add("tool:any(" + "|".join(exp["tools_any"]) + ")",
            any(t in tools for t in exp["tools_any"]), f"called {sorted(set(tools))}")
    for k in exp.get("facts_present", []):
        add(f"fact:{k}", facts.get(k) is not None, "missing")
    for k, v in (exp.get("facts_equal") or {}).items():
        add(f"fact:{k}={v}", facts.get(k) == v, f"got {facts.get(k)}")
    if "period_label" in exp:
        got = (report.get("period") or {}).get("label")
        add(f"period={exp['period_label']}", got == exp["period_label"], f"got {got}")
    if "comparison_label" in exp:
        got = (report.get("comparison") or {}).get("label")
        add(f"comparison={exp['comparison_label']}", got == exp["comparison_label"], f"got {got}")
    if "root_cause" in exp:
        got = (report.get("root_cause") or {}).get("key")
        add(f"root_cause:{exp['root_cause']}", got == exp["root_cause"], f"got {got}")
    for k in exp.get("ruled_out", []):
        h = next((x for x in report.get("hypotheses", []) if x["key"] == k), None)
        add(f"ruled_out:{k}", bool(h and h["status"] == "ruled_out"),
            f"got {h['status'] if h else 'missing'}")
    budget = exp.get("max_steps", 15)
    add("within_budget", report.get("steps_used", 99) <= budget,
        f"{report.get('steps_used')} steps > {budget}")

    # independent metric check (only when the agent reported a headline)
    gt = ground_truth(case.get("period") or (report.get("period") or {}).get("label"),
                      case.get("compare_to") or (report.get("comparison") or {}).get("label"))
    reported = report.get("headline", {}).get("revenue_change_pct")
    if reported is not None:
        add("metric_matches_sql", abs(reported - gt["revenue_pct_change"]) <= TOL,
            f"agent {reported} vs sql {gt['revenue_pct_change']}")

    passed = sum(1 for _, ok, _ in results if ok)
    return {"checks": results, "passed": passed, "total": len(results),
            "ok": passed == len(results), "tools": tools, "ground_truth": gt}


def run(only: str | None = None, out: str | None = None) -> int:
    cases = [c for c in SUITE if not only or c["id"] == only]
    rows, started = [], time.time()
    print(f"Running {len(cases)} evaluation questions\n" + "=" * 92)
    for case in cases:
        t0 = time.time()
        try:
            report = run_investigation(case["question"], case.get("period"), case.get("compare_to"))
            res = check(case, report)
            err = None
        except Exception as e:  # noqa: BLE001
            report, err = {}, f"{type(e).__name__}: {e}"
            res = {"checks": [("run", False, err)], "passed": 0, "total": 1, "ok": False,
                   "tools": [], "ground_truth": {}}
        elapsed = time.time() - t0
        mark = "PASS" if res["ok"] else "FAIL"
        print(f"[{mark}] {case['id']}  {res['passed']}/{res['total']}  {elapsed:5.1f}s  "
              f"{case['question'][:62]}")
        for name, ok, detail in res["checks"]:
            if not ok:
                print(f"         - {name}: {detail}")
        rows.append({"id": case["id"], "question": case["question"], "ok": res["ok"],
                     "passed": res["passed"], "total": res["total"], "seconds": round(elapsed, 2),
                     "tools": res["tools"], "error": err,
                     "failed_checks": [n for n, ok, _ in res["checks"] if not ok],
                     "root_cause": (report.get("root_cause") or {}).get("key"),
                     "confidence": report.get("confidence"), "steps": report.get("steps_used")})

    total_checks = sum(r["total"] for r in rows)
    passed_checks = sum(r["passed"] for r in rows)
    cases_ok = sum(1 for r in rows if r["ok"])
    print("=" * 92)
    print(f"questions passed : {cases_ok}/{len(rows)}  ({cases_ok / len(rows) * 100:.0f}%)")
    print(f"checks passed    : {passed_checks}/{total_checks}  "
          f"({passed_checks / total_checks * 100:.0f}%)")
    print(f"wall clock       : {time.time() - started:.1f}s")

    summary = {"questions": len(rows), "questions_passed": cases_ok,
               "checks": total_checks, "checks_passed": passed_checks,
               "planner": "deterministic/LLM as configured", "results": rows}
    if out:
        path = Path(out) if Path(out).is_absolute() else ROOT / out
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"report written   : {path}")
    return 0 if cases_ok == len(rows) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default=None)
    ap.add_argument("--json", dest="out", default=None)
    a = ap.parse_args()
    raise SystemExit(run(a.id, a.out))
