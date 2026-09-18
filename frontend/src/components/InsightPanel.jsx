import { useState } from 'react'
import { Panel, Stat, Badge, Meter, fmtINR, fmtPct, toneFor } from '../ui.jsx'

function Headline({ h, period, comparison }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <Stat
        label="Revenue change"
        value={fmtPct(h.revenue_change_pct)}
        sub={`${h.revenue_delta_display || '—'} · ${period?.label} vs ${comparison?.label}`}
        tone={toneFor(h.revenue_change_pct)}
      />
      <Stat
        label="Per day (like-for-like)"
        value={fmtPct(h.revenue_change_per_day_pct)}
        sub={`${period?.days}d vs ${comparison?.days}d`}
        tone={toneFor(h.revenue_change_per_day_pct)}
      />
      <Stat
        label="Primary region"
        value={h.primary_region || '—'}
        sub={h.primary_region_share_of_decline_pct
          ? `${h.primary_region_share_of_decline_pct}% of the decline` : undefined}
      />
      <Stat
        label="Primary product"
        value={h.primary_product || '—'}
        sub={h.primary_product_change_pct !== null && h.primary_product_change_pct !== undefined
          ? fmtPct(h.primary_product_change_pct) : undefined}
        tone={toneFor(h.primary_product_change_pct)}
      />
      {h.fill_rate_pct !== null && h.fill_rate_pct !== undefined && (
        <Stat label="Fill rate" value={`${h.fill_rate_pct}%`}
          sub={`${h.stockout_days || 0} stockout days`} tone="text-amber-300" />
      )}
      {h.estimated_impact && (
        <Stat label="Quantified impact" value={h.estimated_impact}
          sub="unserved demand at realised price" tone="text-rose-300" />
      )}
    </div>
  )
}

function CausalChain({ chain }) {
  const [open, setOpen] = useState(true)
  if (!chain?.length) return null
  return (
    <div>
      <button onClick={() => setOpen(!open)}
        className="mb-2 flex w-full items-center justify-between text-[11px] font-semibold
                   uppercase tracking-[0.14em] text-slate-400 hover:text-slate-200">
        <span>Why? — traced mechanism</span>
        <span className="text-slate-600">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <ol className="space-y-1.5">
          {chain.map((c, i) => (
            <li key={i} className="relative rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[12.5px] font-medium text-slate-200">{c.step}</span>
                <span className="font-mono text-[10px] text-slate-600">{c.source}</span>
              </div>
              <div className="mt-0.5 text-[11.5px] leading-snug text-slate-400">{c.detail}</div>
              {i < chain.length - 1 && (
                <div className="absolute -bottom-[7px] left-5 text-slate-700">↓</div>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function Hypotheses({ hypotheses }) {
  const [openKey, setOpenKey] = useState(null)
  if (!hypotheses?.length) return null
  return (
    <div>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
        Hypotheses tested
      </div>
      <ul className="space-y-1.5">
        {hypotheses.map((h) => (
          <li key={h.key} className="rounded-lg border border-slate-800 bg-slate-900/40">
            <button onClick={() => setOpenKey(openKey === h.key ? null : h.key)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left">
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12.5px] text-slate-200">{h.label}</div>
                <div className="mt-1"><Meter value={h.score}
                  tone={h.status === 'supported' ? 'bg-emerald-400'
                    : h.status === 'partial' ? 'bg-amber-400' : 'bg-slate-600'} /></div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="font-mono text-[11px] text-slate-500">{h.score.toFixed(2)}</span>
                <Badge kind={h.status}>{h.status.replace('_', ' ')}</Badge>
              </div>
            </button>
            {openKey === h.key && (
              <div className="border-t border-slate-800/70 px-3 py-2">
                {h.note && <p className="mb-1.5 text-[11.5px] italic text-slate-500">{h.note}</p>}
                <ul className="space-y-1">
                  {h.evidence.map((e, i) => (
                    <li key={i} className="text-[11.5px] leading-snug text-slate-400">
                      <span className="text-slate-300">• {e.claim}</span>
                      <span className="ml-1 font-mono text-[10px] text-slate-600">[{e.source}]</span>
                    </li>
                  ))}
                  {h.evidence.length === 0 && (
                    <li className="text-[11.5px] text-slate-600">Not investigated in this run.</li>
                  )}
                </ul>
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10.5px] leading-snug text-slate-600">
        Scores are strength of evidence, not probabilities of causation.
      </p>
    </div>
  )
}

function Recommendations({ recs }) {
  if (!recs?.length) return null
  return (
    <div>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
        What should we do?
      </div>
      <ol className="space-y-2">
        {recs.map((r, i) => (
          <li key={i} className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2.5">
            <div className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full
                               bg-violet-500/15 text-[11px] font-semibold text-violet-300">
                {r.priority}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[12.5px] leading-snug text-slate-200">{r.action}</p>
                <p className="mt-1 text-[11.5px] leading-snug text-slate-500">{r.why}</p>
                {r.expected_effect && (
                  <p className="mt-1 text-[11.5px] leading-snug text-emerald-400/90">
                    Expected: {r.expected_effect}
                  </p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <Badge kind="info">{r.owner}</Badge>
                  {r.approval_required && <Badge kind="warn">needs approval</Badge>}
                  {r.policy && (
                    <span className="text-[10.5px] text-slate-600">
                      per {r.policy.policy} — {r.policy.section}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

export default function InsightPanel({ report, running }) {
  if (!report) {
    return (
      <Panel title="Business insight" subtitle="Conclusions appear here once the agent finishes"
        bodyClass="flex items-center justify-center p-8">
        <p className="text-center text-xs leading-relaxed text-slate-600">
          {running
            ? 'Investigating… findings are being validated before anything is concluded.'
            : 'No investigation yet.'}
        </p>
      </Panel>
    )
  }

  const conf = report.confidence || 0
  return (
    <Panel
      title="Business insight"
      subtitle={report.objective}
      right={
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Confidence</div>
          <div className={`text-sm font-semibold ${conf >= 0.75 ? 'text-emerald-300'
            : conf >= 0.5 ? 'text-amber-300' : 'text-slate-400'}`}>
            {(conf * 100).toFixed(0)}%
          </div>
        </div>
      }
      bodyClass="scroll-thin max-h-[860px] space-y-4 overflow-y-auto p-4"
    >
      <Headline h={report.headline} period={report.period} comparison={report.comparison} />

      {report.root_cause && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.07] px-3 py-2.5">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-400/90">
            Root cause
          </div>
          <p className="text-[13px] leading-snug text-amber-100">{report.root_cause.statement}</p>
          {report.root_cause.originating_cause && (
            <p className="mt-1 text-[11.5px] text-amber-200/70">
              Originating cause: {report.root_cause.originating_cause}
            </p>
          )}
        </div>
      )}

      {report.narrative && (
        <div>
          <div className="mb-1.5 flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              Executive summary
            </span>
            <Badge kind={report.narrative_source === 'llm' ? 'info' : 'untested'}>
              {report.narrative_source === 'llm' ? 'llm narration' : 'template narration'}
            </Badge>
          </div>
          <p className="text-[12.5px] leading-relaxed text-slate-300">{report.narrative}</p>
        </div>
      )}

      <CausalChain chain={report.causal_chain} />
      <Hypotheses hypotheses={report.hypotheses} />
      <Recommendations recs={report.recommendations} />

      {report.confidence_reasons?.length > 0 && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            How this confidence was reached
          </div>
          <ul className="space-y-0.5">
            {report.confidence_reasons.map((r, i) => (
              <li key={i} className="text-[11.5px] leading-snug text-slate-500">• {r}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="border-t border-slate-800/70 pt-3 text-[10.5px] leading-snug text-slate-600">
        {report.data_notice} Planner: {report.planner}. {report.steps_used} investigative steps.
      </p>
    </Panel>
  )
}
