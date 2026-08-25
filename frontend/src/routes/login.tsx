import { FormEvent, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Eye, EyeOff, KeyRound, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { DEMO_ACCOUNTS } from '@/config/demo-accounts'
import { useAuth } from '@/contexts/auth.context'

/**
 * Localized demo-account display mapping (WP-UX-UA-03).
 *
 * The demo-account module is the machine source of truth for credentials
 * (username / role code / password) and carries English role labels and
 * descriptions only as a non-i18n fallback. Rendering resolves the role
 * label through the shared ``shell:roleLabels`` catalog and the per-role
 * description through ``login:demo.*``, so the login page is fully localized
 * in both locales.
 */
const DEMO_ROLE_LABEL_KEYS: Record<string, string> = {
  PRODUCTION_MANAGER: 'shell:roleLabels.productionManager',
  PROCUREMENT_SPECIALIST: 'shell:roleLabels.procurementSpecialist',
  AUDITOR: 'shell:roleLabels.auditor',
}

const DEMO_DESCRIPTION_KEYS: Record<string, string> = {
  PRODUCTION_MANAGER: 'login:demo.manager.description',
  PROCUREMENT_SPECIALIST: 'login:demo.procurement.description',
  AUDITOR: 'login:demo.auditor.description',
}

export default function Login() {
  const { user, isAuthenticated, isLoading, error, login, clearError } = useAuth()
  const { t } = useTranslation('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [passwordVisible, setPasswordVisible] = useState(false)

  if (isAuthenticated && user) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (isLoading) return
    if (!username.trim() || !password) return
    await login(username.trim(), password)
  }

  const fillDemoAccount = (demoUsername: string, demoPassword: string) => {
    setUsername(demoUsername)
    setPassword(demoPassword)
    clearError()
  }

  const errorMessage = formatError(error, t)

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-steel-900 to-steel-800 px-4 py-8">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold text-primary-400">ForgeMind</h1>
          <p className="text-steel-400">Supply Risk Intelligence</p>
        </div>

        <div className="bg-steel-800/50 border border-steel-700 rounded-lg p-8 space-y-6">
          <h2 className="text-xl font-semibold text-white text-center">
            {t('heading')}
          </h2>

          {errorMessage && (
            <div
              role="alert"
              className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-md px-4 py-3"
              data-testid="login-error"
            >
              {errorMessage}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <label
                htmlFor="username"
                className="block text-sm font-medium text-steel-300"
              >
                {t('username')}
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onFocus={clearError}
                required
                disabled={isLoading}
                className="w-full bg-steel-900 border border-steel-600 rounded-md px-3 py-2 text-white placeholder-steel-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
                data-testid="login-username"
              />
            </div>

            <div className="space-y-2">
              <label
                htmlFor="password"
                className="block text-sm font-medium text-steel-300"
              >
                {t('password')}
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={passwordVisible ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={clearError}
                  required
                  disabled={isLoading}
                  className="w-full bg-steel-900 border border-steel-600 rounded-md px-3 py-2 pr-10 text-white placeholder-steel-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
                  data-testid="login-password"
                />
                <button
                  type="button"
                  onClick={() => setPasswordVisible((visible) => !visible)}
                  aria-label={passwordVisible ? t('hidePassword') : t('showPassword')}
                  className="absolute inset-y-0 right-0 flex items-center px-3 text-steel-400 hover:text-steel-200 focus:outline-none focus:ring-2 focus:ring-primary-500 rounded-r-md"
                  data-testid="login-password-visibility"
                >
                  {passwordVisible ? (
                    <EyeOff className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading || !username.trim() || !password}
              className="w-full bg-primary-600 hover:bg-primary-500 text-white font-medium py-2 px-4 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="login-submit"
            >
              {isLoading ? t('signingIn') : t('signIn')}
            </button>
          </form>
        </div>

        <section
          aria-labelledby="demo-accounts-heading"
          className="space-y-3"
          data-testid="demo-accounts"
        >
          <div className="border-t border-steel-700 pt-4">
            <h2
              id="demo-accounts-heading"
              className="text-sm font-semibold uppercase tracking-wide text-steel-400 flex items-center gap-2"
            >
              <Users className="h-4 w-4" aria-hidden="true" />
              {t('tryDemo')}
            </h2>
          </div>

          <div className="grid grid-cols-1 gap-3">
            {DEMO_ACCOUNTS.map((account) => (
              <div
                key={account.username}
                className="bg-steel-800/50 border border-steel-700 rounded-lg p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
                data-testid={`demo-account-${account.username}`}
              >
                <div className="min-w-0 space-y-1">
                  <h3 className="text-sm font-semibold text-white">
                    {t(DEMO_ROLE_LABEL_KEYS[account.roleCode] ?? 'shell:roleLabels.unknown')}
                  </h3>
                  <p className="text-xs text-steel-400">
                    {t(DEMO_DESCRIPTION_KEYS[account.roleCode] ?? '')}
                  </p>
                  <p className="text-xs font-mono text-primary-400">
                    {account.username}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    fillDemoAccount(account.username, account.password)
                  }
                  disabled={isLoading}
                  className="shrink-0 inline-flex items-center justify-center gap-2 rounded-md border border-primary-500/40 text-primary-300 hover:bg-primary-500/10 px-3 py-1.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  data-testid={`demo-use-${account.username}`}
                >
                  <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('useThisAccount')}
                </button>
              </div>
            ))}
          </div>

          <p className="text-xs text-steel-500">{t('rolesNote')}</p>
        </section>

        <p className="text-center text-xs text-steel-500">{t('credentialsNote')}</p>
      </div>
    </div>
  )
}

function formatError(
  error: ReturnType<typeof useAuth>['error'],
  t: (key: string) => string,
): string | null {
  if (!error) return null
  switch (error) {
    case 'invalid_credentials':
      return t('errors.invalidCredentials')
    case 'backend_unavailable':
      return t('errors.backendUnavailable')
    case 'session_invalid':
      return t('errors.sessionInvalid')
    case 'unknown':
    default:
      return t('errors.unexpected')
  }
}
