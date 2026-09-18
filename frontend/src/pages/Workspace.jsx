import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getJSON, streamInvestigation } from '../api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { Badge, Panel, Stat, fmtPct, toneFor } from '../ui.jsx'
import AskPanel from '../components/AskPanel.jsx'
import ActivityFeed from '../components/ActivityFeed.jsx'
import InsightPanel from '../components/InsightPanel.jsx'
import {
  AnomalyChart, ContributionBars, InventoryChart, RevenueTrend, SimulationCard,
} from '../components/Charts.jsx'

export default function Workspace() {
  const { user, logout } = useAuth()
  const [meta, setMeta] = useState(null)
  const [dash, setDash] = useState(null)
  const [question, setQuestion] = useState(
    'Revenue decreased this month. Find out why and recommend what we should do.')
  const [period, setPeriod] = useState('')
  const [events, setEvents] = useState([])
  const [plan, setPlan] = useState([])
  const [report, setReport] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const closeRef = useRef(null)

  useEffect(() => {
    // A 401 here means the session expired while the tab was open; dropping the
    // user object sends them back through the sign-in route.
    const guard = (e) => (e.status === 401 ? logout() : setError(`API unreachable: ${e.message}`))
    getJSON('/meta').then(setMeta).catch(guard)
    getJSON('/dashboard').then(setDash).catch(guard)
  }, [logout])

  const run = useCallback(() => {
    setEvents([]); setPlan([]); setReport(null); setError(null); setRunning(true)
    closeRef.current = streamInvestigation(
      { question, period },
      (e) => {
        if (e.type === 'plan') setPlan(e.plan || [])
        if (e.type === 'report') { setReport(e.report); setRunning(false) }
        if (e.type === 'run_error') { setError(e.message); setRunning(false) }
        if (e.type === 'done') setRunning(false)
        if (e.type !== 'done') setEvents((prev) => [...prev, e])
      },
    )
  }, [question, period])

  const stop = useCallback(() => { closeRef.current?.(); setRunning(false) }, [])

  const steps = events.filter((e) => e.type === 'finding').length
  const charts = report?.charts || {}
  const showDashboard = !report && !running

  return (
    <div className="min-h-screen bg-[#05080f]">
      <header className="border-b border-slate-800/80 bg-slate-950/60 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-4 px-5 py-3">
          <div className="flex items-baseline gap-3">
            <h1 className="text-[15px] font-semibold tracking-tight text-slate-100">
              Insight<span className="text-sky-400">Pilot</span>
            </h1>
            <span className="hidden text-[11.5px] text-slate-500 sm:inline">
              From “what happened?” to “why?” and “what should we do?”
            </span>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-slate-500">
            {meta?.calendar && (
              <span className="hidden lg:inline">
                data {meta.calendar.data_start} → {meta.calendar.data_end}
              </span>
            )}
            <Badge kind="warn">synthetic data</Badge>
            <Link to="/" className="hidden text-slate-400 hover:text-slate-100 sm:inline">
              Overview
            </Link>
            {user && (
              <div className="flex items-center gap-2 border-l border-slate-800 pl-3">
                <span className="flex h-6 w-6 items-center justify-center rounded-full
                                 bg-sky-500/15 text-[10px] font-semibold text-sky-300">
                  {(user.full_name || user.email).slice(0, 1).toUpperCase()}
                </span>
                <span className="hidden text-slate-400 md:inline" title={user.email}>
                  {user.full_name}{user.is_demo ? ' · demo' : ''}
                </span>
                <button onClick={logout}
                  className="rounded-md border border-slate-700 px-2 py-1 text-[11px]
                             text-slate-300 transition hover:border-slate-500">
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1800px] gap-4 px-5 py-4
                       lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[330px_minmax(0,1fr)_430px]">
        <div className="space-y-4">
          <AskPanel {...{ question, setQuestion, period, setPeriod, running, meta, error }}
            onRun={run} onStop={stop} />
        </div>

        <div className="space-y-4">
          <ActivityFeed events={events} running={running} plan={plan} steps={steps} />

          {showDashboard && dash && (
            <>
              <Panel title="Current position"
                subtitle={`${dash.period.label} vs ${dash.comparison.label} — the dashboard view, before anyone asks why`}
                bodyClass="p-4">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Stat label="Revenue" value={dash.display.revenue}
                    sub={`prev ${dash.display.previous_revenue}`} />
                  <Stat label="Change" value={fmtPct(dash.summary.change.revenue_pct)}
                    sub={dash.display.delta}
                    tone={toneFor(dash.summary.change.revenue_pct)} />
                  <Stat label="Per day" value={fmtPct(dash.summary.change.revenue_per_day_pct)}
                    sub="like-for-like" tone={toneFor(dash.summary.change.revenue_per_day_pct)} />
                  <Stat label="Orders" value={dash.summary.current.orders.toLocaleString()}
                    sub={fmtPct(dash.summary.change.orders_pct)} />
                </div>
                {dash.inventory_alerts?.length > 0 && (
                  <div className="mt-3 rounded-lg border border-amber-500/25 bg-amber-500/[0.06] px-3 py-2">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-400/90">
                      Availability alerts this period
                    </div>
                    <ul className="mt-1 space-y-0.5">
                      {dash.inventory_alerts.slice(0, 4).map((a, i) => (
                        <li key={i} className="text-[11.5px] text-amber-100/80">
                          {a.product_name} · {a.region_id} — {a.stockout_days} stockout days,
                          {' '}{a.units_lost} units unserved
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Panel>

              <div className="grid gap-4 xl:grid-cols-2">
                <RevenueTrend points={dash.trend} period={dash.period.start.slice(0, 7)} />
                <ContributionBars rows={dash.regions} title="Regional contribution"
                  subtitle="Change in revenue vs the prior period" />
              </div>
            </>
          )}

          {(report || running) && (
            <div className="grid gap-4 xl:grid-cols-2">
              <RevenueTrend points={charts.revenue_trend} period={report?.period?.start?.slice(0, 7)} />
              <ContributionBars rows={charts.breakdown_region?.rows} title="Regional contribution"
                subtitle="Change in revenue vs the prior period" />
              <ContributionBars rows={charts.breakdown_product_scoped?.rows || charts.breakdown_product?.rows}
                title="Product movers"
                subtitle={charts.breakdown_product_scoped?.args?.region_id
                  ? `Inside ${charts.breakdown_product_scoped.args.region_id}` : 'Company-wide'} />
              <AnomalyChart entities={charts.anomalies} />
              <InventoryChart daily={charts.inventory_daily} scope={charts.inventory_scope} />
              <SimulationCard sim={charts.simulation} />
            </div>
          )}

          {charts.purchase_orders?.length > 0 && (
            <Panel title="Supplier deliveries" subtitle="Worst-delayed consignments in the window"
              bodyClass="scroll-thin overflow-x-auto p-0">
              <table className="w-full text-left text-[11.5px]">
                <thead className="bg-slate-900/60 text-[10px] uppercase tracking-wider text-slate-500">
                  <tr>
                    {['PO', 'Product', 'Supplier', 'Warehouse', 'Promised', 'Received', 'Delay'].map((h) => (
                      <th key={h} className="px-3 py-2 font-semibold">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {charts.purchase_orders.map((po) => (
                    <tr key={po.po_id} className="border-t border-slate-800/60">
                      <td className="px-3 py-1.5 font-mono text-slate-400">{po.po_id}</td>
                      <td className="px-3 py-1.5 text-slate-300">{po.product_id}</td>
                      <td className="px-3 py-1.5 text-slate-400">{po.supplier_name}</td>
                      <td className="px-3 py-1.5 text-slate-400">{po.warehouse_id}</td>
                      <td className="px-3 py-1.5 text-slate-500">{po.promised_date}</td>
                      <td className="px-3 py-1.5 text-slate-500">{po.received_date}</td>
                      <td className={`px-3 py-1.5 font-semibold ${po.delay_days > 5 ? 'text-rose-400'
                        : po.delay_days > 2 ? 'text-amber-400' : 'text-slate-500'}`}>
                        +{po.delay_days}d
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </div>

        <div className="xl:sticky xl:top-4 xl:self-start">
          <InsightPanel report={report} running={running} />
        </div>
      </main>

      <footer className="mx-auto max-w-[1800px] px-5 pb-6 pt-2 text-[10.5px] leading-snug text-slate-600">
        InsightPilot · agentic root-cause investigation over a synthetic consumer-electronics dataset.
        Figures are computed in SQL and pandas and validated before the language model narrates them.
      </footer>
    </div>
  )
}
