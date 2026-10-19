import Icon from '../../components/Icon'
import RiskBadge from '../../components/RiskBadge'
import type { ForecastWindowResponse } from '../../types/weather'
import ForecastSlider from './ForecastSlider'
import HeatmapLegend from './HeatmapLegend'
import { formatInchesPerHour, formatLocalDateTime, formatMiles, formatMph } from './format'
import { worstState, type HeatmapPoint } from './heatmap'
import { WEATHER_REASON_TEXT, type CheckpointRiskState } from './riskDisplay'

export type ForecastState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'failed'; message: string }
  | { status: 'done'; window: ForecastWindowResponse }

interface ForecastHeatmapPanelProps {
  enabled: boolean
  onToggle: (enabled: boolean) => void
  forecast: ForecastState
  onRetry: () => void
  departureIso: string
  offsetHours: number
  onOffsetChange: (offsetHours: number) => void
  routeLabel: string
  points: HeatmapPoint[] | null
  /** Worst risk along the route for each hour of the window. */
  timeline?: CheckpointRiskState[] | null
}

/** Worst state at the selected hour and the checkpoints that have it. */
function HourSummary({ points, routeLabel }: { points: HeatmapPoint[]; routeLabel: string }) {
  const worst = worstState(points.map((point) => point.state))
  const where = points.filter((point) => point.state === worst).map((point) => `#${point.checkpoint.index}`)
  const shown =
    where.length === points.length && points.length > 1
      ? `all ${points.length} checkpoints`
      : `checkpoint ${where.length > 4 ? `${where.slice(0, 4).join(', ')} +${where.length - 4} more` : where.join(', ')}`
  return (
    <div className="heatmap-summary">
      <span className="heatmap-summary__label">Worst on {routeLabel} at this hour</span>
      <span className="heatmap-summary__value">
        <RiskBadge level={worst} />
        {worst !== 'unavailable' && <span className="heatmap-summary__where">at {shown}</span>}
      </span>
    </div>
  )
}

interface HeatmapTableProps {
  points: HeatmapPoint[]
  offsetHours: number
  /** Forecast hour used for this slot; rows mention their own only when it differs. */
  slotForecastTime: string | null
}

function HeatmapTable({ points, offsetHours, slotForecastTime }: HeatmapTableProps) {
  const hour = slotForecastTime ? formatLocalDateTime(slotForecastTime) : 'no forecast hour'
  return (
    <details className="heatmap-table">
      <summary>Show heatmap values as a table</summary>
      <div className="heatmap-table__scroll">
        <table>
          <caption>
            Conditions at +{offsetHours} h ({hour}), not at each checkpoint&rsquo;s ETA
          </caption>
          <thead>
            <tr>
              <th scope="col">Checkpoint</th>
              <th scope="col">Wind · Rain · Snow</th>
              <th scope="col">Risk</th>
            </tr>
          </thead>
          <tbody>
            {points.map(({ checkpoint, observation, state }) => {
              const weather = observation?.weather
              const available = weather?.status === 'available' && observation?.risk
              const ownHour =
                weather?.forecast_time && weather.forecast_time !== slotForecastTime ? weather.forecast_time : null
              return (
                <tr key={checkpoint.index}>
                  <th scope="row">
                    #{checkpoint.index}
                    <span className="heatmap-table__sub">{formatMiles(checkpoint.distance_miles)}</span>
                  </th>
                  <td>
                    {available && weather ? (
                      <span className="heatmap-table__metrics">
                        <span>{weather.wind_speed_mph !== null ? formatMph(weather.wind_speed_mph) : '—'}</span>
                        <span>{weather.rain_in_per_hr !== null ? formatInchesPerHour(weather.rain_in_per_hr) : '—'}</span>
                        <span>
                          {weather.snowfall_in_per_hr !== null ? formatInchesPerHour(weather.snowfall_in_per_hr) : '—'}
                        </span>
                      </span>
                    ) : (
                      <span className="heatmap-table__reason">
                        {weather?.reason ? WEATHER_REASON_TEXT[weather.reason] : 'No forecast data.'}
                      </span>
                    )}
                    {ownHour && (
                      <span className="heatmap-table__sub">Forecast hour {formatLocalDateTime(ownHour)}</span>
                    )}
                  </td>
                  <td>
                    <RiskBadge level={state} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function ForecastHeatmapPanel({
  enabled,
  onToggle,
  forecast,
  onRetry,
  departureIso,
  offsetHours,
  onOffsetChange,
  routeLabel,
  points,
  timeline = null,
}: ForecastHeatmapPanelProps) {
  const forecastWindow = forecast.status === 'done' ? forecast.window : null
  const slot = forecastWindow?.slots.find((s) => s.offset_hours === offsetHours) ?? null

  return (
    <section className="heatmap-panel" aria-labelledby="heatmap-heading">
      <div className="heatmap-panel__header">
        <h3 id="heatmap-heading">
          <Icon name="layers" className="text-brand-400" />
          Weather heatmap (0–48 h)
        </h3>
        <label className="toggle">
          <input type="checkbox" checked={enabled} onChange={(event) => onToggle(event.target.checked)} />
          Show weather heatmap
        </label>
      </div>

      {!enabled && (
        <p className="heatmap-panel__hint">
          Colour {routeLabel} by forecast risk for any hour in the next 48 h.
        </p>
      )}

      {enabled && forecast.status === 'loading' && (
        <p className="banner banner--info" role="status">
          Loading the 48-hour forecast along the routes…
        </p>
      )}

      {enabled && forecast.status === 'failed' && (
        <div className="banner banner--error" role="alert">
          <p className="banner__title">Heatmap unavailable</p>
          <p>{forecast.message} No heatmap is shown.</p>
          <button type="button" className="button button--small" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}

      {enabled && forecastWindow && (
        <>
          {points && <HourSummary points={points} routeLabel={routeLabel} />}
          <ForecastSlider
            departureIso={departureIso}
            offsetHours={offsetHours}
            forecastTime={slot?.forecast_time ?? null}
            onChange={onOffsetChange}
            timeline={timeline}
          />
          {forecastWindow.coverage_note && (
            <p className="banner banner--warning" role="note">
              {forecastWindow.coverage_note}
            </p>
          )}
          <HeatmapLegend />
          <p className="heatmap-panel__notice" role="note">
            Conditions at the <strong>selected hour</strong> everywhere on {routeLabel}; each stretch
            takes its nearest checkpoint&rsquo;s forecast. This is not radar, and not where your truck
            will be then: see checkpoint ETAs.
          </p>
          {points && (
            <HeatmapTable points={points} offsetHours={offsetHours} slotForecastTime={slot?.forecast_time ?? null} />
          )}
        </>
      )}
    </section>
  )
}

export default ForecastHeatmapPanel
