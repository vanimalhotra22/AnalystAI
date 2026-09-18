import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext.jsx'
import Landing from './pages/Landing.jsx'
import AuthPage from './pages/AuthPage.jsx'
import Workspace from './pages/Workspace.jsx'

function Splash({ label }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#05080f]">
      <div className="text-center">
        <div className="running-dot mx-auto h-2.5 w-2.5 rounded-full bg-sky-400" />
        <p className="mt-4 text-[12px] text-slate-500">{label}</p>
      </div>
    </div>
  )
}

/** Sends signed-out visitors to /login, remembering where they were heading. */
function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Splash label="Restoring your session…" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />
        <Route path="/app" element={<RequireAuth><Workspace /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
