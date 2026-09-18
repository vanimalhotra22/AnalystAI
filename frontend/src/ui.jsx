// Small shared primitives and formatters.

export function fmtINR(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const v = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (v >= 1e7) return `${sign}₹${(v / 1e7).toFixed(2)} Cr`
  if (v >= 1e5) return `${sign}₹${(v / 1e5).toFixed(2)} L`
  if (v >= 1e3) return `${sign}₹${(v / 1e3).toFixed(1)} K`
  return `${sign}₹${v.toFixed(0)}`
}

export function fmtPct(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value > 0 ? '+' : ''}${Number(value).toFixed(digits)}%`
}

export const toneFor = (v) => (v === null || v === undefined ? 'text-slate-400'
  : v < 0 ? 'text-rose-400' : v > 0 ? 'text-emerald-400' : 'text-slate-300')

export function Panel({ title, subtitle, right, className = '', bodyClass = '', children }) {
  return (
    <section className={`panel flex flex-col ${className}`}>
      {(title || right) && (
        <header className="flex items-start justify-between gap-3 border-b border-slate-800/80 px-4 py-3">
          <div>
            <h2 className="text-[13px] font-semibold uppercase tracking-[0.13em] text-slate-300">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      <div className={`flex-1 ${bodyClass}`}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, sub, tone = 'text-slate-100' }) {
  return (
    <div className="rounded-lg border border-slate-800/80 bg-slate-900/40 px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold leading-tight ${tone}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-slate-500">{sub}</div>}
    </div>
  )
}

const BADGE = {
  supported: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  partial: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  ruled_out: 'border-slate-600/50 bg-slate-700/20 text-slate-400',
  untested: 'border-slate-700/50 bg-slate-800/30 text-slate-500',
  info: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
  warn: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  danger: 'border-rose-500/40 bg-rose-500/10 text-rose-300',
}

export function Badge({ kind = 'info', children }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px]
      font-semibold uppercase tracking-wider ${BADGE[kind] || BADGE.info}`}>
      {children}
    </span>
  )
}

export function Meter({ value, tone = 'bg-sky-400' }) {
  const pct = Math.max(0, Math.min(1, value || 0)) * 100
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
    </div>
  )
}
