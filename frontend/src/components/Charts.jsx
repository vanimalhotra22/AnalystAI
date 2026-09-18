import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ReferenceArea,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { Panel, fmtINR, fmtPct } from '../ui.jsx'

const AXIS = { stroke: '#475569', fontSize: 10, tickLine: false }
const GRID = { stroke: '#1e293b', strokeDasharray: '3 3' }

function TT({ active, payload, label, render }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border border-slate-700 bg-slate-950/95 px-2.5 py-1.5 text-[11px] shadow-xl">
      <div className="mb-0.5 font-semibold text-slate-300">{label}</div>
      {render ? render(payload) : payload.map((p, i) => (
        <div key={i} className="text-slate-400">
          {p.name}: <span className="text-slate-100">{fmtINR(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

export function RevenueTrend({ points, period }) {
  if (!points?.length) return null
  return (
    <Panel title="Revenue trend" subtitle="Monthly, with the investigated month highlighted"
      bodyClass="p-3">
      <ResponsiveContainer width="100%" height={190}>
        <AreaChart data={points} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid {...GRID} vertical={false} />
          <XAxis dataKey="period" {...AXIS} />
          <YAxis {...AXIS} width={52} tickFormatter={(v) => `${(v / 1e7).toFixed(1)}Cr`} />
          <Tooltip content={<TT />} />
          {period && <ReferenceArea x1={period} x2={period} fill="#f59e0b" fillOpacity={0.12} />}
          <Area type="monotone" dataKey="revenue" name="Revenue" stroke="#38bdf8" strokeWidth={2}
            fill="url(#rev)" dot={{ r: 2, fill: '#0ea5e9' }} />
        </AreaChart>
      </ResponsiveContainer>
    </Panel>
  )
}

export function ContributionBars({ rows, title, subtitle }) {
  if (!rows?.length) return null
  const data = [...rows].sort((a, b) => a.delta - b.delta).slice(0, 8)
    .map((r) => ({ ...r, short: (r.label || r.key).replace(/^Smart|^Pure|^Groom|^Chef/i, '').slice(0, 18) }))
  return (
    <Panel title={title} subtitle={subtitle} bodyClass="p-3">
      <ResponsiveContainer width="100%" height={Math.max(170, data.length * 26)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid {...GRID} horizontal={false} />
          <XAxis type="number" {...AXIS} tickFormatter={(v) => `${(v / 1e5).toFixed(0)}L`} />
          <YAxis type="category" dataKey="short" {...AXIS} width={110} />
          <Tooltip content={<TT render={(p) => (
            <>
              <div className="text-slate-400">change: <span className="text-slate-100">{fmtINR(p[0].payload.delta)}</span></div>
              <div className="text-slate-400">vs prior: <span className="text-slate-100">{fmtPct(p[0].payload.pct_change)}</span></div>
              <div className="text-slate-400">share of decline: <span className="text-slate-100">{p[0].payload.share_of_decline_pct}%</span></div>
            </>
          )} />} />
          <Bar dataKey="delta" name="Change" radius={[0, 3, 3, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.delta < 0 ? '#f43f5e' : '#34d399'} fillOpacity={d.delta < 0 ? 0.85 : 0.7} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Panel>
  )
}

export function InventoryChart({ daily, scope }) {
  if (!daily?.length) return null
  const runs = []
  let start = null
  daily.forEach((d, i) => {
    if (d.stockout && start === null) start = d.date
    const ends = !d.stockout || i === daily.length - 1
    if (ends && start !== null) { runs.push([start, daily[i].stockout ? d.date : daily[i - 1].date]); start = null }
  })
  const label = [scope?.product_id, scope?.region_id].filter(Boolean).join(' · ')
  return (
    <Panel title="Inventory ledger" subtitle={`Closing stock and unserved demand${label ? ` — ${label}` : ''}`}
      bodyClass="p-3">
      <ResponsiveContainer width="100%" height={190}>
        <ComposedChart data={daily} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid {...GRID} vertical={false} />
          <XAxis dataKey="date" {...AXIS} tickFormatter={(v) => v.slice(8)} />
          <YAxis {...AXIS} width={34} />
          <Tooltip content={<TT render={(p) => (
            <>
              <div className="text-slate-400">closing stock: <span className="text-slate-100">{p[0]?.payload.closing_stock}</span></div>
              <div className="text-slate-400">sold: <span className="text-slate-100">{p[0]?.payload.units_sold}</span></div>
              <div className="text-slate-400">unserved: <span className="text-rose-300">{p[0]?.payload.units_lost}</span></div>
            </>
          )} />} />
          {runs.map(([a, b], i) => (
            <ReferenceArea key={i} x1={a} x2={b} fill="#f43f5e" fillOpacity={0.14} />
          ))}
          <Area type="stepAfter" dataKey="closing_stock" name="Closing stock" stroke="#38bdf8"
            strokeWidth={2} fill="#38bdf8" fillOpacity={0.12} dot={false} />
          <Bar dataKey="units_lost" name="Unserved units" fill="#f43f5e" radius={[2, 2, 0, 0]} />
          <Line type="monotone" dataKey="units_sold" name="Units sold" stroke="#34d399"
            strokeWidth={1.5} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="mt-1 px-1 text-[10.5px] text-slate-600">
        Shaded bands are days the ledger recorded a stockout.
      </p>
    </Panel>
  )
}

export function AnomalyChart({ entities }) {
  if (!entities?.length) return null
  const data = entities.map((e) => ({
    x: e.pct_change, y: e.anomaly_score, z: Math.abs(e.current_revenue),
    label: e.label, flagged: e.is_anomaly, z_score: e.z_score,
  }))
  return (
    <Panel title="Anomaly scan" subtitle="Movement vs anomaly score (robust z-score + IsolationForest)"
      bodyClass="p-3">
      <ResponsiveContainer width="100%" height={190}>
        <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid {...GRID} />
          <XAxis type="number" dataKey="x" name="change" {...AXIS}
            tickFormatter={(v) => `${v.toFixed(0)}%`} />
          <YAxis type="number" dataKey="y" name="score" {...AXIS} width={34} domain={[0, 1]} />
          <ZAxis type="number" dataKey="z" range={[40, 260]} />
          <Tooltip content={<TT render={(p) => (
            <>
              <div className="text-slate-100">{p[0]?.payload.label}</div>
              <div className="text-slate-400">change: {fmtPct(p[0]?.payload.x)}</div>
              <div className="text-slate-400">anomaly score: {p[0]?.payload.y}</div>
              <div className="text-slate-400">z: {p[0]?.payload.z_score}</div>
            </>
          )} />} />
          <Scatter data={data}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.flagged ? '#f59e0b' : '#334155'}
                fillOpacity={d.flagged ? 0.9 : 0.6} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </Panel>
  )
}

export function SimulationCard({ sim }) {
  if (!sim || sim.error) return null
  const { current_policy: c, uplifted_policy: u, economics: e, assumption: a } = sim
  return (
    <Panel title="What-if simulation"
      subtitle={`+${u.safety_stock_uplift_pct}% safety stock · ${a.trials} Monte-Carlo trials`}
      bodyClass="space-y-3 p-4">
      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 py-2.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Current risk</div>
          <div className="mt-1 text-xl font-semibold text-rose-300">{c.stockout_probability_pct}%</div>
          <div className="text-[10.5px] text-slate-600">{c.expected_stockout_days_per_90d} days / 90</div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 py-2.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">With uplift</div>
          <div className="mt-1 text-xl font-semibold text-emerald-300">{u.stockout_probability_pct}%</div>
          <div className="text-[10.5px] text-slate-600">{u.expected_stockout_days_per_90d} days / 90</div>
        </div>
      </div>
      <div className="space-y-1 text-[11.5px]">
        <Row k="Protected revenue" v={e.protected_revenue_display} tone="text-emerald-300" />
        <Row k="Extra holding cost" v={e.additional_holding_cost_display} tone="text-amber-300" />
        <Row k="Net benefit / 90 days" v={e.net_benefit_display} tone="text-sky-300" />
      </div>
      <p className="text-[10.5px] leading-snug text-slate-600">{sim.caveat}</p>
    </Panel>
  )
}

function Row({ k, v, tone }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-800/60 pb-1">
      <span className="text-slate-500">{k}</span>
      <span className={`font-semibold ${tone}`}>{(v || '')}</span>
    </div>
  )
}
