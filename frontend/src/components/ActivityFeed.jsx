import { useEffect, useRef } from 'react'
import { Panel, Badge } from '../ui.jsx'

const ICON = {
  run_started: '▸', status: '·', understanding: '◈', plan: '≡', tool_start: '⟳',
  finding: '✓', hypothesis: '⚖', causal_chain: '⤷', root_cause: '★',
  recommendation: '→', narrative: '¶', report: '■', error: '!',
}

const TONE = {
  finding: 'text-emerald-300', tool_start: 'text-sky-300', root_cause: 'text-amber-300',
  recommendation: 'text-violet-300', error: 'text-rose-300', hypothesis: 'text-slate-300',
}

const SHOWN = new Set([
  'run_started', 'status', 'understanding', 'plan', 'tool_start', 'finding',
  'hypothesis', 'root_cause', 'recommendation', 'narrative', 'error',
])

export default function ActivityFeed({ events, running, plan, steps }) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [events.length])

  const visible = events.filter((e) => SHOWN.has(e.type))

  return (
    <Panel
      title="Live investigation"
      subtitle="Every step the agent took, in the order it decided to take it"
      right={
        <div className="flex items-center gap-2">
          {steps > 0 && <span className="text-[11px] text-slate-500">{steps} steps</span>}
          {running
            ? <span className="running-dot inline-block h-2 w-2 rounded-full bg-sky-400" />
            : events.length > 0 && <Badge kind="supported">done</Badge>}
        </div>
      }
      bodyClass="relative"
    >
      {plan?.length > 0 && (
        <div className="border-b border-slate-800/70 bg-slate-950/40 px-4 py-3">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            Plan
          </div>
          <ol className="space-y-1 text-[11px] leading-snug text-slate-500">
            {plan.map((p, i) => <li key={i}>{i + 1}. {p}</li>)}
          </ol>
        </div>
      )}

      <div className="scroll-thin max-h-[520px] min-h-[220px] overflow-y-auto px-4 py-3">
        {visible.length === 0 && (
          <p className="py-10 text-center text-xs text-slate-600">
            Ask a question to start an investigation.
          </p>
        )}
        <ul className="space-y-2">
          {visible.map((e, i) => (
            <li key={i} className="step-in flex gap-2.5 text-[12.5px] leading-snug">
              <span className={`mt-[3px] w-3 shrink-0 text-center text-[11px] ${TONE[e.type] || 'text-slate-600'}`}>
                {ICON[e.type] || '·'}
              </span>
              <div className="min-w-0 flex-1">
                <span className={e.type === 'status' ? 'text-slate-500' : 'text-slate-200'}>
                  {e.message}
                </span>
                {e.type === 'tool_start' && (
                  <div className="mt-0.5 font-mono text-[10.5px] text-slate-600">
                    {e.tool}({Object.entries(e.args || {}).map(([k, v]) => `${k}=${v}`).join(', ')})
                  </div>
                )}
                {e.type === 'finding' && e.elapsed_ms !== undefined && (
                  <div className="mt-0.5 font-mono text-[10.5px] text-slate-600">
                    {e.tool} · {e.elapsed_ms} ms
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
        <div ref={endRef} />
      </div>
    </Panel>
  )
}
