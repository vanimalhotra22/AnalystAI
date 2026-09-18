import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'

const MIN_PASSWORD = 8

function Field({ id, label, hint, ...props }) {
  return (
    <label htmlFor={id} className="block">
      <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
        {label}
      </span>
      <input
        id={id}
        {...props}
        className="w-full rounded-lg border border-slate-700/80 bg-slate-950/70 px-3 py-2.5
                   text-[13.5px] text-slate-100 outline-none transition
                   placeholder:text-slate-600 focus:border-sky-500/60 focus:ring-1 focus:ring-sky-500/30"
      />
      {hint && <span className="mt-1 block text-[11px] text-slate-600">{hint}</span>}
    </label>
  )
}

export default function AuthPage({ mode }) {
  const isSignup = mode === 'signup'
  const { user, login, signup, demoLogin } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from || '/app'

  const [form, setForm] = useState({ email: '', password: '', full_name: '', company: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)

  if (user) return <Navigate to={from} replace />

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const clientCheck = () => {
    if (!form.email.includes('@')) return 'Enter a valid email address.'
    if (isSignup && form.password.length < MIN_PASSWORD)
      return `Password must be at least ${MIN_PASSWORD} characters.`
    if (!form.password) return 'Enter your password.'
    return null
  }

  const submit = async (e) => {
    e.preventDefault()
    const local = clientCheck()
    if (local) return setError(local)
    setError(null)
    setBusy('form')
    try {
      if (isSignup) await signup(form)
      else await login(form.email, form.password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const useDemo = async () => {
    setError(null)
    setBusy('demo')
    try {
      await demoLogin()
      navigate(from, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#05080f]">
      <header className="border-b border-slate-800/70">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
          <Link to="/" className="text-[15px] font-semibold tracking-tight text-slate-100">
            Insight<span className="text-sky-400">Pilot</span>
          </Link>
          <Link to={isSignup ? '/login' : '/signup'} className="text-[12.5px] text-slate-400 hover:text-slate-100">
            {isSignup ? 'Already have an account? Sign in' : 'No account? Create one'}
          </Link>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-5 py-10">
        <div className="grid w-full max-w-4xl gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
          {/* ------------------------------------------------------- pitch */}
          <div className="hidden lg:block">
            <h1 className="text-2xl font-semibold leading-tight tracking-tight text-slate-50">
              {isSignup ? 'Put an open question to your data.' : 'Welcome back.'}
            </h1>
            <p className="mt-3 max-w-md text-[13.5px] leading-relaxed text-slate-400">
              InsightPilot investigates a business question end to end: it plans the queries,
              tests the alternatives, traces the mechanism, and prices the fix — showing every
              step as it goes.
            </p>
            <ul className="mt-6 space-y-2.5 text-[12.5px] text-slate-400">
              {[
                'Numbers computed in SQL and pandas, never by a language model',
                'Ruled-out explanations reported alongside the supported one',
                'Read-only data access with a validated SQL guard',
                'Recommendations cite policy and wait for human approval',
              ].map((line) => (
                <li key={line} className="flex gap-2">
                  <span className="mt-[3px] text-emerald-400">✓</span>
                  <span>{line}</span>
                </li>
              ))}
            </ul>
            <p className="mt-8 text-[11px] leading-relaxed text-slate-600">
              The workspace runs on a synthetic dataset generated for demonstration. It is not
              real company data.
            </p>
          </div>

          {/* -------------------------------------------------------- form */}
          <div className="panel p-6">
            <h2 className="text-[16px] font-semibold text-slate-100">
              {isSignup ? 'Create your account' : 'Sign in'}
            </h2>
            <p className="mt-1 text-[12px] text-slate-500">
              {isSignup ? 'Takes a few seconds. No email verification in this POC.'
                : 'Use your account, or sign in to the shared demo analyst.'}
            </p>

            <form onSubmit={submit} className="mt-5 space-y-3.5" noValidate>
              {isSignup && (
                <>
                  <Field id="full_name" label="Full name" type="text" autoComplete="name"
                    placeholder="Priya Sharma" value={form.full_name} onChange={set('full_name')} />
                  <Field id="company" label="Company" type="text" autoComplete="organization"
                    placeholder="Optional" value={form.company} onChange={set('company')} />
                </>
              )}
              <Field id="email" label="Work email" type="email" autoComplete="email"
                placeholder="you@company.com" value={form.email} onChange={set('email')} required />
              <Field id="password" label="Password" type="password"
                autoComplete={isSignup ? 'new-password' : 'current-password'}
                placeholder={isSignup ? `At least ${MIN_PASSWORD} characters` : '••••••••'}
                hint={isSignup ? 'Stored as a salted scrypt hash — never in plain text.' : undefined}
                value={form.password} onChange={set('password')} required />

              {error && (
                <div role="alert" className="rounded-lg border border-rose-500/40 bg-rose-500/10
                                             px-3 py-2 text-[12px] leading-snug text-rose-300">
                  {error}
                </div>
              )}

              <button type="submit" disabled={busy !== null}
                className="w-full rounded-lg bg-sky-500 px-4 py-2.5 text-[13.5px] font-semibold
                           text-slate-950 transition hover:bg-sky-400 disabled:opacity-50">
                {busy === 'form' ? 'Working…' : isSignup ? 'Create account' : 'Sign in'}
              </button>
            </form>

            <div className="my-4 flex items-center gap-3 text-[11px] text-slate-600">
              <span className="h-px flex-1 bg-slate-800" />or<span className="h-px flex-1 bg-slate-800" />
            </div>

            <button onClick={useDemo} disabled={busy !== null}
              className="w-full rounded-lg border border-slate-700 px-4 py-2.5 text-[13.5px]
                         font-semibold text-slate-200 transition hover:border-slate-500
                         disabled:opacity-50">
              {busy === 'demo' ? 'Signing in…' : 'Continue with the demo account'}
            </button>
            <p className="mt-2 text-center text-[11px] text-slate-600">
              A shared read-only analyst account, so a walkthrough never needs a password.
            </p>

            <p className="mt-5 text-center text-[11px] text-slate-600">
              {isSignup ? 'Already registered? ' : 'New here? '}
              <Link to={isSignup ? '/login' : '/signup'} className="text-sky-400 hover:text-sky-300">
                {isSignup ? 'Sign in' : 'Create an account'}
              </Link>
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
