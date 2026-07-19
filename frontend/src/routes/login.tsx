import { FormEvent, useState } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuth } from '@/contexts/auth.context'

export default function Login() {
  const { user, isAuthenticated, isLoading, error, login, clearError } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  if (isAuthenticated && user) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (isLoading) return
    if (!username.trim() || !password) return
    await login(username.trim(), password)
  }

  const errorMessage = formatError(error)

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-steel-900 to-steel-800 px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold text-primary-400">ForgeMind</h1>
          <p className="text-steel-400">Supply Risk Intelligence</p>
        </div>

        <div className="bg-steel-800/50 border border-steel-700 rounded-lg p-8 space-y-6">
          <h2 className="text-xl font-semibold text-white text-center">
            Sign in
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
                Username
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
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onFocus={clearError}
                required
                disabled={isLoading}
                className="w-full bg-steel-900 border border-steel-600 rounded-md px-3 py-2 text-white placeholder-steel-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
                data-testid="login-password"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading || !username.trim() || !password}
              className="w-full bg-primary-600 hover:bg-primary-500 text-white font-medium py-2 px-4 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="login-submit"
            >
              {isLoading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-steel-500">
          Authorized use only. Contact your administrator for credentials.
        </p>
      </div>
    </div>
  )
}

function formatError(error: ReturnType<typeof useAuth>['error']): string | null {
  if (!error) return null
  switch (error) {
    case 'invalid_credentials':
      return 'Invalid username or password.'
    case 'backend_unavailable':
      return 'Authentication service is unavailable. Please try again later.'
    case 'session_invalid':
      return 'Your session has expired. Please sign in again.'
    case 'unknown':
    default:
      return 'An unexpected error occurred. Please try again.'
  }
}
