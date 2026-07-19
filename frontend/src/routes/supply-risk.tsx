/**
 * Supply Risk Analysis foundation — WP-3.3 placeholder.
 *
 * No risk list. No business data.
 * WP-3.5 will populate this surface with the supply-risk table.
 */
export default function SupplyRisk() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="max-w-md space-y-3 text-center">
        <h1 className="text-2xl font-semibold text-white">Supply Risk Analysis</h1>
        <p className="text-sm text-steel-400">
          Risk list, filters and evidence panels will be rendered here.
        </p>
        <div className="rounded border border-steel-700 bg-steel-800/40 px-4 py-3">
          <p className="text-xs text-steel-500">
            Risk analysis — available in WP-3.5
          </p>
        </div>
      </div>
    </div>
  )
}
