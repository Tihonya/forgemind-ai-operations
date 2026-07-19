/**
 * Dashboard foundation — WP-3.3 placeholder.
 *
 * No widgets. No business data. No metrics.
 * WP-3.4 will populate this surface with real backend data.
 */
export default function Dashboard() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="max-w-md space-y-3 text-center">
        <h1 className="text-2xl font-semibold text-white">Executive Dashboard</h1>
        <p className="text-sm text-steel-400">
          Operational overview and active supply-risk indicators will be populated here.
        </p>
        <div className="rounded border border-steel-700 bg-steel-800/40 px-4 py-3">
          <p className="text-xs text-steel-500">
            Dashboard widgets — available in WP-3.4
          </p>
        </div>
      </div>
    </div>
  )
}
