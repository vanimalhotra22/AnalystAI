import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'

const TRACE = [
  ['Revenue ₹4.34 Cr vs ₹4.59 Cr — -5.5% total, -8.5% per day', 'measure'],
  ['North carries 76.5% of the decline (-17.7%)', 'localise'],
  ['Anomaly scan inside North: SmartAir Purifier 3000i, z = -3.46', 'ml'],
  ['Demand 79 units, served 39 → fill rate 49.4%', 'supply'],
  ['Inventory ledger: 17 stockout days, 01–17 July', 'supply'],
  ['PO-000214 promised 02-Jul, received 18-Jul — 16 days late', 'upstream'],
  ['Marketing in North -36.5% — contributing driver', 'test'],
  ['Pricing +0.07 pts, customers -3.5% — ruled out', 'test'],
  ['Impact ₹8.93 L of demand not captured', 'quantify'],
]

const TAG_TONE = {
  measure: 'text-sky-300', localise: 'text-sky-300', ml: 'text-violet-300',
  supply: 'text-amber-300', upstream: 'text-amber-300', test: 'text-slate-400',
  quantify: 'text-rose-300',
}

function TraceDemo() {
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setShown((n) => (n >= TRACE.length ? 0 : n + 1)), 900)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center gap-2 border-b border-slate-800/80 px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-rose-500/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber-500/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/70" />
        <span className="ml-2 text-[11px] text-slate-500">live investigation</span>
        {shown < TRACE.length && (
          <span className="running-dot ml-auto inline-block h-2 w-2 rounded-full bg-sky-400" />
        )}
      </div>
      <ul className="min-h-[248px] space-y-1.5 px-4 py-3 font-mono text-[11.5px] leading-relaxed">
        {TRACE.slice(0, shown).map(([line, tag], i) => (
          <li key={i} className="step-in flex gap-2">
            <span className="text-emerald-400">✓</span>
            <span className={TAG_TONE[tag]}>{line}</span>
          </li>
        ))}
        {shown === TRACE.length && (
          <li className="step-in mt-2 rounded-md border border-amber-500/30 bg-amber-500/[0.07] px-2.5 py-2 text-amber-100">
            root cause · inventory shortage from a 16-day supplier delay · confidence 80%
          </li>
        )}
      </ul>
    </div>
  )
}

function Stat({ value, label }) {
  return (
    <div>
      <div className="text-xl font-semibold text-slate-100 sm:text-2xl">{value}</div>
      <div className="mt-0.5 text-[11px] uppercase tracking-[0.14em] text-slate-500">{label}</div>
    </div>
  )
}

function Feature({ title, body, tag }) {
  return (
    <div className="panel p-4">
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-sky-400/80">
        {tag}
      </div>
      <h3 className="text-[14px] font-semibold text-slate-100">{title}</h3>
      <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-400">{body}</p>
    </div>
  )
}

export default function Landing() {
  const { user } = useAuth()

  return (
    <div className="min-h-screen bg-[#05080f]">
      {/* ---------------------------------------------------------------- nav */}
      <header className="sticky top-0 z-20 border-b border-slate-800/70 bg-[#05080f]/85 backdrop-blur">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
          <Link to="/" className="text-[15px] font-semibold tracking-tight text-slate-100">
            Insight<span className="text-sky-400">Pilot</span>
          </Link>
          <div className="hidden items-center gap-6 text-[12.5px] text-slate-400 md:flex">
            <a href="#gap" className="hover:text-slate-100">The gap</a>
            <a href="#how" className="hover:text-slate-100">How it works</a>
            <a href="#capabilities" className="hover:text-slate-100">Capabilities</a>
            <a href="#stack" className="hover:text-slate-100">Stack</a>
          </div>
          <div className="flex items-center gap-2">
            {user ? (
              <Link to="/app" className="rounded-lg bg-sky-500 px-3.5 py-1.5 text-[12.5px]
                font-semibold text-slate-950 hover:bg-sky-400">
                Open workspace
              </Link>
            ) : (
              <>
                <Link to="/login" className="rounded-lg px-3 py-1.5 text-[12.5px] text-slate-300
                  hover:text-slate-100">Sign in</Link>
                <Link to="/signup" className="rounded-lg bg-sky-500 px-3.5 py-1.5 text-[12.5px]
                  font-semibold text-slate-950 hover:bg-sky-400">Get started</Link>
              </>
            )}
          </div>
        </nav>
      </header>

      {/* -------------------------------------------------------------- hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute -top-40 left-1/2 h-[420px] w-[820px]
                        -translate-x-1/2 rounded-full bg-sky-500/10 blur-3xl" />
        <div className="relative mx-auto grid max-w-6xl gap-10 px-5 py-16 lg:grid-cols-2 lg:py-20">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-700/70
                             bg-slate-900/60 px-3 py-1 text-[11px] text-slate-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Agentic BI · root-cause investigation
            </span>
            <h1 className="mt-5 text-3xl font-semibold leading-[1.15] tracking-tight text-slate-50 sm:text-[44px]">
              From <span className="text-slate-400">“what happened?”</span> to
              <span className="text-sky-400"> “why?”</span> and
              <span className="text-emerald-400"> “what should we do?”</span>
            </h1>
            <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-slate-400">
              Dashboards report the number. InsightPilot investigates it — planning its own
              queries, testing the explanations it expects to be innocent, tracing the
              mechanism upstream, pricing the impact, and proposing an action a human signs off.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link to={user ? '/app' : '/signup'}
                className="rounded-lg bg-sky-500 px-5 py-2.5 text-[13.5px] font-semibold
                           text-slate-950 transition hover:bg-sky-400">
                {user ? 'Open workspace' : 'Start investigating'}
              </Link>
              <Link to="/login"
                className="rounded-lg border border-slate-700 px-5 py-2.5 text-[13.5px]
                           font-semibold text-slate-200 transition hover:border-slate-500">
                Use the demo account
              </Link>
            </div>
            <p className="mt-4 text-[11.5px] text-slate-600">
              Runs offline with no API key — an explicit investigation policy plans the steps
              until you configure a model.
            </p>

            <div className="mt-9 grid grid-cols-2 gap-6 border-t border-slate-800/70 pt-6 sm:grid-cols-4">
              <Stat value="232K" label="rows analysed" />
              <Stat value="14" label="agent tools" />
              <Stat value="~4s" label="per investigation" />
              <Stat value="34/34" label="eval questions" />
            </div>
          </div>

          <div className="lg:pt-6">
            <TraceDemo />
            <p className="mt-3 text-center text-[11px] text-slate-600">
              An actual run, replayed. Every line is computed in SQL or pandas — never written
              by a language model.
            </p>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------- gap */}
      <section id="gap" className="border-y border-slate-800/70 bg-slate-950/40">
        <div className="mx-auto max-w-6xl px-5 py-14">
          <h2 className="text-xl font-semibold tracking-tight text-slate-100">
            The gap between a dashboard and a decision
          </h2>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="panel p-5">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                Today
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-slate-400">
                “Revenue is down 5.5%.” The dashboard has done its job. Now an analyst spends an
                hour opening the warehouse: regions, then products, then inventory, then
                suppliers, then marketing, then pricing — writing a query, reading it, deciding
                what to ask next.
              </p>
              <ul className="mt-3 space-y-1 text-[12.5px] text-slate-500">
                <li>• the question is open-ended, the dashboard is not</li>
                <li>• the cause usually lives in a different table from the symptom</li>
                <li>• most of the work is deciding what to look at next</li>
              </ul>
            </div>
            <div className="panel border-sky-500/25 p-5">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-400/80">
                With InsightPilot
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-slate-300">
                Ask in plain English. The agent plans an investigation, runs it against the
                warehouse, and comes back with a ranked explanation, the evidence behind it, the
                alternatives it ruled out, the rupee impact, and a costed recommendation.
              </p>
              <ul className="mt-3 space-y-1 text-[12.5px] text-slate-400">
                <li>• picks each step from what the previous step returned</li>
                <li>• separates a supply constraint from a demand shift, with a measured test</li>
                <li>• every figure traceable to a table and a date range</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------- how */}
      <section id="how" className="mx-auto max-w-6xl px-5 py-14">
        <h2 className="text-xl font-semibold tracking-tight text-slate-100">How a run unfolds</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[
            ['01', 'Understand', 'Classifies the intent, resolves the period from the question, and drafts an investigation plan.'],
            ['02', 'Investigate', 'One tool per step — measure, localise, scan for anomalies, test supply before demand — each chosen from the last result.'],
            ['03', 'Validate', 'Six hypotheses scored against the gathered facts. The innocent ones are ruled out on the record, not ignored.'],
            ['04', 'Recommend', 'Impact in rupees, a Monte-Carlo on the proposed fix, the policy clause it follows, and a human approval flag.'],
          ].map(([n, title, body]) => (
            <div key={n} className="panel p-4">
              <div className="font-mono text-[11px] text-sky-400/70">{n}</div>
              <h3 className="mt-1.5 text-[14px] font-semibold text-slate-100">{title}</h3>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-400">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------ capabilities */}
      <section id="capabilities" className="border-y border-slate-800/70 bg-slate-950/40">
        <div className="mx-auto max-w-6xl px-5 py-14">
          <h2 className="text-xl font-semibold tracking-tight text-slate-100">
            What is actually under the hood
          </h2>
          <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <Feature tag="orchestration" title="A supervisor that decides"
              body="A LangGraph loop performs one tool call per visit and re-plans, so the investigation is as long as the evidence requires — fourteen steps for an open 'why', three for a direct question." />
            <Feature tag="no hallucinated numbers" title="Python computes, the model narrates"
              body="Every metric comes from parameterised SQL and pandas. The model chooses what to compute and writes the summary; it never does arithmetic on business data." />
            <Feature tag="machine learning" title="Anomalies, not eyeballing"
              body="Robust z-scores against each entity's own twelve-month history plus IsolationForest for multivariate outliers — so a real break is separated from ordinary month-to-month noise." />
            <Feature tag="evidence" title="Ruled-out alternatives, on the record"
              body="Pricing, marketing, customer churn and demand softness are each scored and reported. An explanation that never says what it isn't cannot be audited." />
            <Feature tag="decision support" title="What-if, priced"
              body="A Monte-Carlo inventory simulation on the product's own demand history and the supplier's own lead times turns 'raise safety stock' into a net rupee figure." />
            <Feature tag="governance" title="Read-only by construction"
              body="SELECT-only validation, a schema allow-list, row caps, a read-only connection, and human approval on anything that costs money." />
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- stack */}
      <section id="stack" className="mx-auto max-w-6xl px-5 py-14">
        <h2 className="text-xl font-semibold tracking-tight text-slate-100">Stack</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Frontend', 'React · Tailwind · Recharts · React Router'],
            ['Backend', 'FastAPI · Pydantic · SQLAlchemy · SSE'],
            ['Agent', 'LangGraph supervisor · 14 typed tools · TF-IDF policy retrieval'],
            ['Data & ML', 'PostgreSQL / SQLite · pandas · NumPy · scikit-learn'],
          ].map(([k, v]) => (
            <div key={k} className="panel p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{k}</div>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-300">{v}</p>
            </div>
          ))}
        </div>
      </section>

      {/* --------------------------------------------------------------- cta */}
      <section className="border-t border-slate-800/70">
        <div className="mx-auto max-w-6xl px-5 py-14 text-center">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-100">
            Ask it why.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-[13.5px] leading-relaxed text-slate-400">
            Create an account, or sign in to the demo analyst, and put an open-ended business
            question to the agent.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Link to={user ? '/app' : '/signup'}
              className="rounded-lg bg-sky-500 px-5 py-2.5 text-[13.5px] font-semibold
                         text-slate-950 hover:bg-sky-400">
              {user ? 'Open workspace' : 'Create an account'}
            </Link>
            <Link to="/login"
              className="rounded-lg border border-slate-700 px-5 py-2.5 text-[13.5px]
                         font-semibold text-slate-200 hover:border-slate-500">
              Sign in
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-800/70">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-6 text-[11px]
                        leading-relaxed text-slate-600 sm:flex-row sm:items-center sm:justify-between">
          <span>InsightPilot · agentic business-intelligence investigation.</span>
          <span>
            All data is synthetic and generated for demonstration. It is not real company data.
          </span>
        </div>
      </footer>
    </div>
  )
}
