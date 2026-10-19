import RiskBadge from '../../components/RiskBadge'
import type { EvaluatedRoute } from '../../types/routes'
import { formatLocalDateTime, formatMiles } from './format'
import { checkpointRiskState } from './riskDisplay'

interface CheckpointListProps {
  route: EvaluatedRoute
  selectedIndex: number
  onSelect: (index: number) => void
}

function CheckpointList({ route, selectedIndex, onSelect }: CheckpointListProps) {
  return (
    <section className="checkpoint-list" aria-labelledby="checkpoint-list-heading">
      <h3 id="checkpoint-list-heading">
        Route {route.provider_order + 1} checkpoints ({route.checkpoints.length})
      </h3>
      <p className="section-caption">Risk when the truck arrives at each checkpoint (ETA).</p>
      <ol>
        {route.checkpoints.map((checkpoint) => (
          <li key={checkpoint.index}>
            <button
              type="button"
              className="checkpoint-row"
              aria-pressed={checkpoint.index === selectedIndex}
              onClick={() => onSelect(checkpoint.index)}
            >
              <span className="checkpoint-row__index">#{checkpoint.index}</span>
              <span>{formatMiles(checkpoint.distance_miles)}</span>
              <span className="checkpoint-row__eta">{formatLocalDateTime(checkpoint.eta)}</span>
              <RiskBadge level={checkpointRiskState(checkpoint)} />
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}

export default CheckpointList
