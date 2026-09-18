# InsightPilot

**From "what happened?" to "why?" and "what should we do?"**

An agentic business-intelligence layer that investigates a business question instead of
just answering it. A manager asks *"Revenue decreased this month — why, and what should we
do?"*; the agent plans an investigation, queries the warehouse, runs statistics, tests and
rules out alternative explanations, traces the mechanism upstream, quantifies the impact in
rupees, cites the governing policy, and proposes actions that a human still has to approve.

> **Synthetic data notice.** Every figure in this project comes from a generated dataset
> (*SmartHealth Consumer Analytics*) created purely for demonstration. It is not real
> company data and does not represent any real organisation.

---

## What it does, in one run

Question: *"Revenue decreased this month. Find out why and recommend what we should do."*

```
✓ Revenue ₹4.34 Cr vs ₹4.59 Cr  →  -5.5% total, -8.5% per day (31d vs 30d)
✓ North carries 76.5% of the decline (-17.7%)
✓ Anomaly scan inside North: SmartAir Purifier 3000i, z = -3.46
✓ Product ranking: SmartAir Purifier 3000i -61.2% (-₹13.74 L)
✓ Demand 79 units, served 39 → fill rate 49.4%  ⇒ supply-side, not demand-side
✓ Inventory ledger: 17 stockout days, 2026-07-01 → 2026-07-17, 40 units unserved
✓ Upstream: PO-000214 (AirTech Components) promised 07-02, received 07-18 — 16 days late
✓ Marketing in North -36.5%  → contributing driver
✓ Pricing +0.07 pts, customers -3.5%  → ruled out
✓ Impact ₹8.93 L of demand not captured
✓ Policy: Class A safety stock ≥ 15% of lead-time demand, alert at 7 days cover
```

**Root cause:** inventory shortage of SmartAir Purifier 3000i in North (17 stockout days),
originating from a 16-day supplier delivery delay. **Confidence 80%**, with the reasons for
that number stated. Fourteen investigative steps, about four seconds.

---

## Why this is an agent, not a chatbot

| | Prompt → answer | RAG chatbot | **InsightPilot** |
|---|---|---|---|
| Chooses its own next step | ✗ | ✗ | ✓ each step depends on the previous finding |
| Multi-step tool use | ✗ | retrieval only | ✓ 14 typed tools over SQL, pandas, ML, policy docs |
| Tests alternative explanations | ✗ | ✗ | ✓ six hypotheses scored, the innocent ones ruled out |
| Numbers are verifiable | ✗ | ✗ | ✓ computed in SQL/pandas, checked against independent SQL in the eval suite |
| Ends in a decision | ✗ | ✗ | ✓ recommendations, costed, cited, gated on human approval |

The investigation is not a fixed pipeline. The supervisor picks the next tool from what it
has learned: it drills into the region carrying the money, scans for anomalies there, and
only walks up the supply chain **because** the fill-rate test came back at 49%.

---

## Quickstart

Requires Python 3.11+ and Node 18+.

**1. Install and generate the dataset** (~20 s, ~232,000 rows):

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```

```bash
cd backend && ../.venv/Scripts/python -m app.data.generate
```

**2. Start the API** (http://127.0.0.1:8000):

```bash
cd backend && ../.venv/Scripts/python -m uvicorn app.api.main:app --reload
```

**3. Start the UI** (http://localhost:5173):

```bash
cd frontend && npm install && npm run dev
```

Open `/` for the landing page, then either create an account or press **Continue with the
demo account** — a one-click sign-in that exists so a live walkthrough never involves typing
a password (`demo@insightpilot.local`, disable with `DEMO_ACCOUNT_ENABLED=false`).

No API key is needed — see *Planning* below. To let a model plan the investigation, copy
`.env.example` to `.env` and set `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GOOGLE_API_KEY`.

To run against PostgreSQL instead of the default SQLite file, set
`DATABASE_URL` / `READONLY_DATABASE_URL` as shown in `.env.example`, and regenerate.

---

## Architecture

```
                 Manager
                    │
                    ▼
        Landing page → sign up / sign in      React Router · session in an httpOnly cookie
                    │  natural-language business question
                    ▼
        React + Tailwind + Recharts          three panes: ask · live investigation · insight
                    │  SSE, one event per agent step
                    ▼
             FastAPI  (/api/investigate/stream, guarded)
                    │
                    ▼
        ┌──────────────────────────┐
        │   SUPERVISOR (LangGraph) │  understand → investigate ⟲ → validate → conclude → narrate
        └───────────┬──────────────┘
                    │ picks one tool per step
     ┌──────────────┼───────────────┬──────────────────┐
     ▼              ▼               ▼                  ▼
  SQL tools    Analysis tools   ML tools          Knowledge tool
 (SQLAlchemy)  (pandas/NumPy)  (scikit-learn)     (TF-IDF over policy docs)
     │              │               │                  │
     ▼              ▼               ▼                  ▼
 PostgreSQL /   metrics, trends,  IsolationForest,   inventory · supplier ·
 SQLite (RO)    contributions     robust z-score,    pricing · marketing ·
                                  Monte-Carlo        reporting policies
     └──────────────┴───────────────┴──────────────────┘
                    ▼
          Evidence validation  →  six hypotheses scored: supported / partial / ruled out
                    ▼
          Root cause + causal chain  →  every link carries a number and its source table
                    ▼
          Recommendations  →  costed, policy-cited, human-approval flagged
```

Full detail: [`docs/architecture.md`](docs/architecture.md).

### The four design decisions that matter

**1. The model never produces a number.** SQL and pandas compute; the model chooses what to
compute and narrates the result. Each tool returns `summary` (English with the real numbers
in it), `data` (structured, drives the charts), and `facts` (scalars the scorer reads). The
activity feed shows tool-generated summaries, so it stays true even if narration is switched
off entirely.

**2. Conclusions come from an explicit scorer, not from the model.** Six hypotheses —
stockout, supplier delay, marketing, pricing, customer churn, demand softness — each have a
readable scoring function over the gathered facts, returning a status, a strength-of-evidence
score, and the evidence with its source table. Ruled-out hypotheses are reported too: an
explanation that never says what it *isn't* cannot be audited. Scores are labelled strength
of evidence, **not** probability of causation.

**3. SQL access is guarded three ways.** A validator (single statement, SELECT/WITH only, no
DDL/DML verbs, no comment smuggling, schema allow-list, row cap), a read-only connection
(SQLite `mode=ro`, or a SELECT-only Postgres role — `scripts/init_readonly_role.sql`), and
parameterised filters from a fixed allow-list. `backend/tests/test_guardrails.py` proves the
refusals.

**4. Planning degrades gracefully.** With an API key the LLM supervisor chooses each step.
Without one — or if a provider call fails mid-run — an explicit deterministic investigation
policy takes over, driving the same tools and the same scorer. The UI always shows which
planner is running. That is why this demo works offline, on a plane, with no API budget.

---

## Accounts and access

The product surface is a landing page, sign-up, sign-in and the guarded workspace.

| | |
|---|---|
| Passwords | salted **scrypt** (stdlib, memory-hard), constant-time comparison, never stored or logged in plain text |
| Sessions | signed JWT in an **httpOnly, SameSite=Lax** cookie — page scripts cannot read it, and `EventSource` still authenticates, which matters because the investigation stream is SSE and cannot send an `Authorization` header |
| Scripted clients | the same token works as `Authorization: Bearer …` |
| Sign-up rules | email format, minimum length, common-password and email-lookalike rejection |
| Brute force | per-IP + per-email failure window; repeated failures return `429` with a wait time |
| Enumeration | login failures are indistinguishable, and a verification is always run so a missing account and a wrong password take similar time |
| Protected | `/api/meta`, `/api/dashboard`, `/api/policies`, `/api/sql`, `/api/investigate*` — `/api/health` stays public for probes |
| Demo account | one-click sign-in for walkthroughs; `DEMO_ACCOUNT_ENABLED=false` removes it |

Accounts live in their own `MetaData`, so regenerating the synthetic dataset (which drops and
rebuilds every analytics table) never touches them. Twenty tests cover this — hashing,
lockout, tampered tokens, and a parametrised check that every analytics route 401s without a
session (`backend/tests/test_auth.py`).

Set `JWT_SECRET` before deploying anywhere real; without it the API starts on a development
key and logs a warning.

---

## What is in the data

Nineteen months (Jan 2025 – Jul 2026) of a fictional consumer-health / smart-home business:
24 products, 5 regions, 6 suppliers, 9,000 customers, ≈232,000 rows.

| table | rows | what it carries |
|---|---:|---|
| `sales` | 145,161 | line-level revenue, cost, discount, channel, customer |
| `inventory` | 69,240 | daily stock ledger per product-warehouse, including **unserved demand** |
| `marketing` | 6,840 | monthly spend, impressions, clicks, conversions |
| `purchase_orders` | 2,250 | promised vs received dates, delay days |
| `customers` | 9,000 | segment, region, age group, acquisition channel |
| `products` / `regions` / `suppliers` / `channels` | 39 | dimensions |

The generator (`backend/app/data/generate.py`) is **mechanistic, not decorative**: it
simulates daily demand, depletes stock against it, raises purchase orders against supplier
lead times, and records sales as the portion of demand inventory could actually serve. A
customs hold on one supplier therefore genuinely *causes* a stockout, which genuinely
*causes* the revenue decline — so the agent is discovering a real chain in the data, not
reciting a hard-coded story. Decoys (stable pricing, stable customer mix, on-time suppliers)
are there to be ruled out.

---

## Evaluation

34 business questions with machine-checkable expectations — intent, tool selection, resolved
period, facts, root cause, ruled-out alternatives, step budget — plus a check that the
agent's headline figure matches an **independently written SQL query**.

```bash
cd backend && ../.venv/Scripts/python -m app.eval.runner --json docs/eval_report.json
```

```
questions passed : 34/34  (100%)
checks passed    : 150/150 (100%)
wall clock       : 35.7s
```

Unit and integration tests (61, including the SQL-guard refusals, the auth guards and an
end-to-end investigation):

```bash
cd backend && ../.venv/Scripts/python -m pytest
```

---

## Project layout

```
backend/app/
  config.py              settings; SQLite by default, Postgres by env var
  db/                    schema (SQLAlchemy Core) + read/write and read-only engines
  data/                  product catalogue and the mechanistic dataset generator
  analytics/             periods · metrics · anomaly detection · impact & simulation
  agents/                sql_tool · tools · knowledge (RAG) · planner · scoring ·
                         report · llm · graph (LangGraph) · state
  auth/                  users table · scrypt hashing · JWT sessions · route guard
  api/main.py            REST + server-sent events
  eval/                  34-question suite and its runner
  tests/                 pytest: guardrails, analytics, auth, end-to-end agent
frontend/src/
  pages/                 Landing · AuthPage (sign in / sign up) · Workspace
  auth/AuthContext.jsx   session state, shared by the router guard
  components/            AskPanel · ActivityFeed · InsightPanel · Charts
docs/policies/           five synthetic policy documents (the RAG corpus)
docs/                    architecture · demo script · interview notes · eval report
scripts/                 Postgres read-only role
```

---

## Honest limitations

- **Semi-autonomous by design.** The agent investigates on its own; anything with financial
  or operational consequence is flagged `approval_required` and left to a human.
- **Evidence, not proof.** Correlation within a single month is reported as evidence. The one
  place a mechanism is genuinely demonstrated is unserved demand in the inventory ledger, and
  that distinction is stated in the output rather than glossed over.
- **The impact figure is an upper bound.** It assumes unserved demand was lost rather than
  deferred or substituted — stated in the tool output and in the report.
- **The what-if simulation inherits history**, including the disruption itself, so it is a
  planning aid, not a forecast.
- **Retrieval is TF-IDF**, which is deterministic and offline but weaker on paraphrase than
  embeddings; swapping in FAISS is a change behind `knowledge.search()`.
- **The LLM planning path needs a key.** Without one the deterministic policy runs, and the
  UI says so rather than pretending a model is driving.
