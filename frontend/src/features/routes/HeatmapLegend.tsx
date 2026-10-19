import { LEGEND_STATES, RISK_COLORS, RISK_LABELS, RISK_SYMBOLS } from './riskDisplay'

function HeatmapLegend() {
  return (
    <div className="heatmap-legend">
      <p className="heatmap-legend__title" id="heatmap-legend-title">
        Risk legend
      </p>
      <ul aria-labelledby="heatmap-legend-title">
        {LEGEND_STATES.map((state) => (
          <li key={state}>
            <span
              className={`heatmap-legend__swatch heatmap-legend__swatch--${state}`}
              style={{ backgroundColor: RISK_COLORS[state] }}
              aria-hidden="true"
            />
            <span aria-hidden="true" className="heatmap-legend__symbol">
              {RISK_SYMBOLS[state]}
            </span>
            {RISK_LABELS[state]}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default HeatmapLegend
