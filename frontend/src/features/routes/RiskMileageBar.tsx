import type { RouteRiskSummary } from '../../types/routes'
import { formatMiles } from './format'
import { riskSegments } from './riskDisplay'

function RiskMileageBar({ summary }: { summary: RouteRiskSummary }) {
  const total = summary.total_distance_miles
  if (total <= 0) return null
  const segments = riskSegments(summary)
  const description = segments.map((s) => `${s.label} ${formatMiles(s.miles)}`).join(', ')

  return (
    <div className="grid gap-1.5">
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-white/5"
        role="img"
        aria-label={`Risk by distance: ${description}`}
        data-testid="risk-mileage-bar"
      >
        {segments.map(
          (s) =>
            s.miles > 0 && (
              <span
                key={s.key}
                className="h-full first:rounded-l-full last:rounded-r-full"
                style={{ width: `${(s.miles / total) * 100}%`, backgroundColor: s.color }}
              />
            ),
        )}
      </div>
      <ul className="m-0 flex list-none flex-wrap gap-x-3 gap-y-0.5 p-0 text-[0.7rem] text-slate-400" aria-hidden="true">
        {segments
          .filter((s) => s.miles > 0)
          .map((s) => (
            <li key={s.key} className="inline-flex items-center gap-1">
              <span className="size-2 rounded-full" style={{ backgroundColor: s.color }} />
              {s.label} {Math.round((s.miles / total) * 100)}%
            </li>
          ))}
      </ul>
    </div>
  )
}

export default RiskMileageBar
