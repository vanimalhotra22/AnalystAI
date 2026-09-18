"""FastAPI surface.

Two ways to run an investigation:
  POST /api/investigate         synchronous, returns the finished report (used by
                                the evaluation harness and any scripted caller);
  GET  /api/investigate/stream  server-sent events, one per agent step, so the UI
                                can show the investigation as it happens.

Plus a dashboard endpoint so the front end has something to show before anyone
asks a question, and a guarded /api/sql endpoint that demonstrates the SQL
validator (including its refusals).
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
import math
import queue
import threading
import uuid
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agents import knowledge
from app.agents.graph import run_investigation
from app.auth import service as auth_service
from app.auth.routes import router as auth_router
from app.agents.llm import get_llm
from app.agents.sql_tool import SQLGuardError, run_sql
from app.agents.tools import default_context, tool_specs
from app.analytics import metrics as M
from app.analytics.periods import describe_calendar, resolve_comparison, resolve_period
from app.config import settings
from app.db.session import ro_engine
from sqlalchemy import text

log = logging.getLogger("insightpilot")

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create the users table and the demo account before serving traffic."""
    auth_service.init_auth_storage()
    auth_service.ensure_demo_account()
    if not settings.jwt_secret:
        log.warning("JWT_SECRET is not set - using the development signing key. "
                    "Set JWT_SECRET before deploying anywhere real.")
    yield


app = FastAPI(title="InsightPilot", version="0.2.0",
              description="Agentic business-intelligence investigation over a synthetic dataset.",
              lifespan=lifespan)

# Credentialed CORS cannot use a wildcard origin, and the session lives in a
# cookie -- so the dev origins are listed explicitly.  In production this is the
# one deployed origin, and the UI is usually served from the same one anyway.
DEV_ORIGINS = [f"http://{host}:{port}" for host in ("localhost", "127.0.0.1")
               for port in (5173, 5183, 4173, 3000)]

cors_origins = list(DEV_ORIGINS)
if settings.cors_origins:
    cors_origins.extend([o.strip() for o in settings.cors_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$" if settings.allow_vercel_preview else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


SUGGESTED_QUESTIONS = [
    "Revenue decreased this month. Find out why and recommend what we should do.",
    "Why did revenue decline in July 2026?",
    "Which region performed worst last month?",
    "Which products have abnormal inventory?",
    "Why did SmartAir Purifier 3000i revenue fall in North?",
    "Is our supplier delivery performance getting worse?",
    "Did the marketing spend cut in North hurt revenue?",
    "What if we increase safety stock by 15%?",
]


class InvestigateRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    period: str | None = None
    compare_to: str | None = None


class SQLRequest(BaseModel):
    sql: str = Field(min_length=6, max_length=4000)


# ------------------------------------------------------------------ basics
@app.get("/api/health")
def health() -> dict:
    with ro_engine().connect() as c:
        rows = {t: c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                for t in ("sales", "inventory", "marketing", "purchase_orders", "customers", "products")}
    return {"status": "ok", "database": settings.database_url.split("/")[-1], "row_counts": rows,
            "llm": get_llm().describe(), "calendar": describe_calendar(),
            "policies": knowledge.corpus_summary(),
            "auth": {"demo_account_enabled": settings.demo_account_enabled,
                     "signing_key": "configured" if settings.jwt_secret else "development default"}}


@app.get("/api/meta")
def meta(user: dict = Depends(auth_service.current_user)) -> dict:
    with ro_engine().connect() as c:
        regions = [dict(r._mapping) for r in c.execute(text(
            "SELECT region_id, region_name FROM regions ORDER BY region_name"))]
        products = [dict(r._mapping) for r in c.execute(text(
            "SELECT product_id, product_name, category FROM products ORDER BY product_name"))]
    return {"regions": regions, "products": products,
            "calendar": describe_calendar(), "suggested_questions": SUGGESTED_QUESTIONS,
            "tools": [{"name": t["name"], "description": t["description"]} for t in tool_specs()],
            "llm": get_llm().describe(),
            "data_notice": "Synthetic demonstration dataset - not real company data."}


@app.get("/api/dashboard")
def dashboard(period: str | None = None, compare_to: str | None = None,
              user: dict = Depends(auth_service.current_user)) -> dict:
    cur = resolve_period(period)
    prev = resolve_comparison(cur, compare_to)
    summary = M.revenue_summary(cur, prev)
    regions = M.breakdown("region", cur, prev)
    products = M.breakdown("product", cur, prev, top_n=6)
    inv = M.inventory_health(cur)
    return {
        "period": cur.as_dict(), "comparison": prev.as_dict(),
        "summary": summary,
        "trend": M.trend(cur, months=13)["points"],
        "regions": regions["rows"],
        "product_movers": products["rows"],
        "inventory_alerts": [r for r in inv.get("by_product_region", []) if r["stockout_days"] > 0][:6],
        "display": {
            "revenue": M.fmt_inr(summary["current"]["revenue"]),
            "previous_revenue": M.fmt_inr(summary["previous"]["revenue"]),
            "delta": M.fmt_inr(summary["change"]["revenue_delta"]),
        },
    }


@app.get("/api/policies")
def policies(q: str | None = None, user: dict = Depends(auth_service.current_user)) -> dict:
    if q:
        return {"query": q, "results": knowledge.search(q, k=5)}
    return knowledge.corpus_summary()


@app.post("/api/sql")
def sql(req: SQLRequest, user: dict = Depends(auth_service.current_user)) -> dict:
    """Read-only ad-hoc query. Demonstrates the validator, refusals included."""
    try:
        res = run_sql(req.sql)
    except SQLGuardError as e:
        raise HTTPException(status_code=400, detail=f"SQL guard: {e}") from e
    return {"sql": res.sql, "columns": res.columns, "rows": res.rows,
            "row_count": res.row_count, "truncated": res.truncated, "elapsed_ms": res.elapsed_ms}


# ----------------------------------------------------------- investigation
@app.post("/api/investigate")
def investigate(req: InvestigateRequest,
                user: dict = Depends(auth_service.current_user)) -> dict:
    return _jsonable(run_investigation(req.question, req.period, req.compare_to))


@app.get("/api/investigate/stream")
async def investigate_stream(
    question: str = Query(min_length=3, max_length=500),
    period: str | None = None,
    compare_to: str | None = None,
    user: dict = Depends(auth_service.current_user),
):
    """Server-sent events: one event per agent action, then the final report."""
    run_id = uuid.uuid4().hex[:12]
    events: queue.Queue = queue.Queue()
    SENTINEL = object()

    def emit(event: dict) -> None:
        events.put(event)

    def worker() -> None:
        try:
            run_investigation(question, period, compare_to, emit=emit, run_id=run_id)
        except Exception as e:  # noqa: BLE001 - surface it to the UI, never hang the stream
            events.put({"type": "run_error", "message": f"{type(e).__name__}: {e}"})
        finally:
            events.put(SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    async def stream():
        loop = asyncio.get_running_loop()
        while True:
            item = await loop.run_in_executor(None, events.get)
            if item is SENTINEL:
                yield {"event": "done", "data": json.dumps({"run_id": run_id})}
                return
            yield {"event": item.get("type", "message"),
                   "data": json.dumps(_jsonable(item), default=str)}

    return EventSourceResponse(stream())


def _jsonable(obj: Any) -> Any:
    """JSON-safe: dates become ISO strings and NaN/Infinity become null, because
    both are legal in Python's json module but not in the JSON a browser parses."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj
