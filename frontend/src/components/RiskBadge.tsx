import {
  RISK_LABELS,
  RISK_SYMBOLS,
  type CheckpointRiskState,
} from '../features/routes/riskDisplay'

interface RiskBadgeProps {
  level: CheckpointRiskState
  /** Optional prefix such as "Wind" for screen readers and sighted users alike. */
  label?: string
}

function RiskBadge({ level, label }: RiskBadgeProps) {
  return (
    <span className={`risk-badge risk-badge--${level}`}>
      <span aria-hidden="true" className="risk-badge__symbol">
        {RISK_SYMBOLS[level]}
      </span>
      {label ? `${label}: ` : ''}
      {RISK_LABELS[level]}
    </span>
  )
}

export default RiskBadge
