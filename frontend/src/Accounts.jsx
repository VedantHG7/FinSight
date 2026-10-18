import { createContext, useContext, useEffect, useState } from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, setCsrf } from './api'
import logo from './assets/finsight-logo.jpg'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [account, setAccount] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const accept = data => { setCsrf(data.csrf_token); setAccount(data); setError('') }
  const refresh = async () => {
    setLoading(true)
    try { accept(await api('/auth/me')) }
    catch (err) { setAccount(null); if (!err.message.includes('sign in')) setError(err.message) }
    finally { setLoading(false) }
  }
  useEffect(() => {
    refresh()
    const expired = () => { setAccount(null); setCsrf(''); localStorage.removeItem('finsight:analysisId') }
    window.addEventListener('finsight:session-expired', expired)
    return () => window.removeEventListener('finsight:session-expired', expired)
  }, [])
  const logout = async () => {
    await api('/auth/logout', { method: 'POST' })
    setCsrf(''); setAccount(null); localStorage.removeItem('finsight:analysisId')
  }
  return <AuthContext.Provider value={{ account, loading, error, accept, logout, refresh }}>{children}</AuthContext.Provider>
}

export function RequireAccount() {
  const { account, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="account-loading" role="status">Opening your workspace…</div>
  return account ? <Outlet /> : <Navigate to="/login" replace state={{ from: location.pathname }} />
}

export function AccountBar() {
  const { account, logout } = useAuth()
  const [error, setError] = useState('')
  return <><header className="workspace-header"><Link className="brand" to="/app"><img src={logo} alt=""/>FinSight</Link><nav aria-label="Workspace"><Link to="/app">Client history</Link><Link to="/app/team">Team</Link>{account.user.role !== 'reviewer' && <Link to="/app/new">New analysis</Link>}<Link to="/app/change-password">Password</Link></nav><div className="account-identity"><span>{account.user.name}<small>{account.organization.name} · {account.user.role}</small></span><button className="secondary-button" onClick={() => logout().catch(err => setError(err.message))}>Sign out</button></div></header>{error && <p role="alert" className="error-text">{error}</p>}</>
}

export function AuthPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const register = location.pathname === '/register'
  const invite = new URLSearchParams(location.search).get('invite') || ''
  const { account, accept, error: connectionError } = useAuth()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (account) return <Navigate to="/app" replace />
  const submit = async event => {
    event.preventDefault(); setBusy(true); setError('')
    const form = new FormData(event.currentTarget)
    try {
      const body = Object.fromEntries(form); if (invite) body.invite_token = invite
      const data = await api(register ? '/auth/register' : '/auth/login', { method: 'POST', body: JSON.stringify(body) })
      accept(data)
      const from = location.state?.from
      navigate(from?.startsWith('/app') ? from : '/app', { replace: true })
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <main className="auth-page"><Link className="brand" to="/"><img src={logo} alt=""/>FinSight</Link><section className="auth-card"><p className="eyebrow">Your financial workspace</p><h1>{register ? invite ? 'Join your team' : 'Create your workspace' : 'Welcome back'}</h1><p>{register ? 'Keep your clients, analyses, and reviews together.' : 'Sign in to pick up where you left off.'}</p><form onSubmit={submit}>
    {register && <label>Full name<input name="full_name" autoComplete="name" required minLength={2} maxLength={120}/></label>}
    {register && !invite && <label>Workspace name<input name="organization" required maxLength={160} placeholder="Your firm or team"/></label>}
    <label>Email address<input name="email" type="email" autoComplete="email" required maxLength={255}/></label>
    <label>Password<input aria-label="Password" name="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} required minLength={register ? 12 : 1} maxLength={256}/>{register && <small>At least 12 characters. A memorable passphrase works well.</small>}</label>
    {(error || connectionError) && <p role="alert" className="error-text">{error || connectionError}</p>}<button className="primary-button" disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'}</button>
  </form>{!register && <p className="auth-switch"><Link to="/forgot-password">Forgot your password?</Link></p>}<p className="auth-switch">{register ? 'Already have an account?' : 'New to FinSight?'} <Link to={register ? '/login' : '/register'}>{register ? 'Sign in' : 'Create a workspace'}</Link></p></section></main>
}

function PasswordLayout({ title, description, children, returnTo = '/login' }) {
  return <main className="auth-page"><Link className="brand" to="/"><img src={logo} alt=""/>FinSight</Link><section className="auth-card"><p className="eyebrow">Account security</p><h1>{title}</h1><p>{description}</p>{children}<p className="auth-switch"><Link to={returnTo}>{returnTo === '/app' ? 'Back to workspace' : 'Back to sign in'}</Link></p></section></main>
}

export function ForgotPasswordPage() {
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const submit = async event => {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    const email = new FormData(event.currentTarget).get('email')
    try { setMessage((await api('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) })).message) }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <PasswordLayout title="Forgot your password?" description="Enter your account email. We will send a link that expires in 30 minutes."><form onSubmit={submit}><label>Email address<input name="email" type="email" autoComplete="email" required maxLength={255}/></label>{error && <p role="alert" className="error-text">{error}</p>}{message && <p role="status">{message}</p>}<button className="primary-button" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</button></form></PasswordLayout>
}

export function ResetPasswordPage() {
  const location = useLocation(), token = new URLSearchParams(location.search).get('token') || ''
  const { refresh } = useAuth()
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const submit = async event => {
    event.preventDefault(); setBusy(true); setError('')
    const form = new FormData(event.currentTarget)
    if (form.get('password') !== form.get('confirm')) { setError('Passwords do not match.'); setBusy(false); return }
    try { setMessage((await api('/auth/reset-password', { method: 'POST', body: JSON.stringify({ token, password: form.get('password') }) })).message); window.history.replaceState(null, '', '/reset-password'); await refresh() }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <PasswordLayout title="Set a new password" description="Choose a password with at least 12 characters.">{!token && <p role="alert" className="error-text">This reset link is missing its token. Request a new link.</p>}{!message && token && <form onSubmit={submit}><label>New password<input name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={256}/></label><label>Confirm new password<input name="confirm" type="password" autoComplete="new-password" required minLength={12} maxLength={256}/></label>{error && <p role="alert" className="error-text">{error}</p>}<button className="primary-button" disabled={busy}>{busy ? 'Updating…' : 'Reset password'}</button></form>}{message && <p role="status">{message}</p>}</PasswordLayout>
}

export function ChangePasswordPage() {
  const { refresh } = useAuth()
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const submit = async event => {
    event.preventDefault(); setBusy(true); setError('')
    const form = new FormData(event.currentTarget)
    if (form.get('new_password') !== form.get('confirm')) { setError('Passwords do not match.'); setBusy(false); return }
    try { setMessage((await api('/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: form.get('current_password'), new_password: form.get('new_password') }) })).message); await refresh() }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <PasswordLayout title="Change your password" description="Changing your password signs you out of all devices." returnTo="/app">{!message && <form onSubmit={submit}><label>Current password<input name="current_password" type="password" autoComplete="current-password" required/></label><label>New password<input name="new_password" type="password" autoComplete="new-password" minLength={12} maxLength={256} required/></label><label>Confirm new password<input name="confirm" type="password" autoComplete="new-password" minLength={12} maxLength={256} required/></label>{error && <p role="alert" className="error-text">{error}</p>}<button className="primary-button" disabled={busy}>{busy ? 'Updating…' : 'Change password'}</button></form>}{message && <p role="status">{message}</p>}</PasswordLayout>
}
