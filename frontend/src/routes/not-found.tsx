import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-steel-900">
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-bold text-primary-400">404</h1>
        <p className="text-steel-300">Page not found</p>
        <Link
          to="/"
          className="text-sm text-primary-400 hover:text-primary-300 underline"
        >
          Return to home
        </Link>
      </div>
    </div>
  )
}
