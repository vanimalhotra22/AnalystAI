import { Panel, Badge } from '../ui.jsx'

export default function AskPanel({
  question, setQuestion, period, setPeriod, running, onRun, onStop, meta, error,
}) {
  const llm = meta?.llm
  const calendar = meta?.calendar
  const periods = ['2026-07', '2026-06', '2026-05', '2026-04', 'Q2 2026']

  return (
    <Panel
      title="Ask the analyst"
      subtitle="A business question in plain English — the agent decides how to investigate it."
      bodyClass="p-4 space-y-4"
    >
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !running) onRun() }}
        rows={4}
        placeholder="e.g. Revenue decreased this month. Find out why and recommend what we should do."
        className="w-full resize-none rounded-lg border border-slate-700/80 bg-slate-950/70 px-3 py-2.5
                   text-sm leading-relaxed text-slate-100 outline-none placeholder:text-slate-600
                   focus:border-sky-500/60 focus:ring-1 focus:ring-sky-500/30"
      />

      <div className="flex items-center gap-2">
        <label className="text-[11px] uppercase tracking-wider text-slate-500">Period</label>
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          className="flex-1 rounded-md border border-slate-700/80 bg-slate-950/70 px-2 py-1.5 text-xs text-slate-200"
        >
          <option value="">Latest complete month{calendar ? ` (${calendar.latest_complete_month})` : ''}</option>
          {periods.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>

      <div className="flex gap-2">
        <button
          onClick={running ? onStop : onRun}
          disabled={!question.trim()}
          className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold transition
            ${running
              ? 'bg-rose-500/15 text-rose-300 border border-rose-500/40 hover:bg-rose-500/25'
              : 'bg-sky-500 text-slate-950 hover:bg-sky-400 disabled:opacity-40 disabled:hover:bg-sky-500'}`}
        >
          {running ? 'Stop investigation' : 'Investigate'}
        </button>
      </div>
      <p className="-mt-2 text-[11px] text-slate-600">Ctrl/⌘ + Enter to run</p>

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </div>
      )}

      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Try one of these
        </div>
        <div className="space-y-1.5">
          {(meta?.suggested_questions || []).map((q) => (
            <button
              key={q}
              onClick={() => setQuestion(q)}
              disabled={running}
              className="w-full rounded-md border border-slate-800 bg-slate-900/50 px-3 py-2 text-left
                         text-xs leading-snug text-slate-400 transition hover:border-sky-600/50
                         hover:bg-slate-800/60 hover:text-slate-200 disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2 border-t border-slate-800/80 pt-3 text-[11px] text-slate-500">
        <div className="flex items-center gap-2">
          <Badge kind={llm?.available ? 'supported' : 'warn'}>
            {llm?.available ? `planner: ${llm.provider}` : 'planner: deterministic'}
          </Badge>
          {llm?.model && <span className="text-slate-600">{llm.model}</span>}
        </div>
        {!llm?.available && (
          <p className="leading-snug">
            No LLM key configured, so the built-in investigation policy is planning the steps.
            Set <code className="text-slate-400">ANTHROPIC_API_KEY</code> (or OpenAI / Gemini) to let
            the model choose them.
          </p>
        )}
        <p className="leading-snug text-slate-600">
          {meta?.data_notice || 'Synthetic demonstration dataset.'}
        </p>
      </div>
    </Panel>
  )
}
