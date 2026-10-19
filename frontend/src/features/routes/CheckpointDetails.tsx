import Icon from '../../components/Icon'
import RiskBadge from '../../components/RiskBadge'
import type { EvaluatedCheckpoint } from '../../types/routes'
import {
  formatInchesPerHour,
  formatLocalDateTime,
  formatMiles,
  formatMph,
} from './format'
import {
  LOAD_RESTRICTION_TEXT,
  WEATHER_REASON_TEXT,
  checkpointRiskState,
} from './riskDisplay'

interface CheckpointDetailsProps {
  checkpoint: EvaluatedCheckpoint
  routeLabel: string
  /** Shorter layout for map popups. */
  compact?: boolean
  /** Hours from departure to this checkpoint's ETA, when the heatmap can show that hour. */
  etaOffsetHours?: number | null
  /** Move the heatmap to this checkpoint's ETA. */
  onShowAtEta?: () => void
}

function CheckpointDetails({
  checkpoint,
  routeLabel,
  compact = false,
  etaOffsetHours = null,
  onShowAtEta,
}: CheckpointDetailsProps) {
  const { weather, risk } = checkpoint
  const loadRule = risk ? LOAD_RESTRICTION_TEXT[risk.load_restriction] : null
  const Heading = compact ? 'p' : 'h3'

  return (
    <section className={`checkpoint-details${compact ? ' checkpoint-details--compact' : ''}`} aria-label="Checkpoint details">
      <Heading className="checkpoint-details__title">
        {routeLabel} · Checkpoint #{checkpoint.index}
      </Heading>
      {!compact && <p className="section-caption">Forecast for when the truck arrives (ETA).</p>}
      <div className="checkpoint-details__overall">
        <RiskBadge level={checkpointRiskState(checkpoint)} label="Overall" />
        {!compact && onShowAtEta && etaOffsetHours !== null && (
          <button type="button" className="button button--small" onClick={onShowAtEta}>
            <Icon name="layers" size={14} />
            Show on heatmap at ETA (+{etaOffsetHours} h)
          </button>
        )}
      </div>

      <dl className="detail-grid">
        <div>
          <dt>From origin</dt>
          <dd>{formatMiles(checkpoint.distance_miles)}</dd>
        </div>
        <div>
          <dt>Estimated arrival</dt>
          <dd>{formatLocalDateTime(checkpoint.eta)}</dd>
        </div>
        <div>
          <dt>Forecast hour used</dt>
          <dd>{weather.forecast_time ? formatLocalDateTime(weather.forecast_time) : 'None'}</dd>
        </div>
      </dl>

      {weather.status === 'available' && risk ? (
        <dl className="detail-grid detail-grid--weather">
          <div>
            <dt>
              <Icon name="wind" size={13} />
              Wind
            </dt>
            <dd>
              {weather.wind_speed_mph !== null ? formatMph(weather.wind_speed_mph) : '—'}{' '}
              <RiskBadge level={risk.wind} />
            </dd>
          </div>
          <div>
            <dt>
              <Icon name="rain" size={13} />
              Rain
            </dt>
            <dd>
              {weather.rain_in_per_hr !== null ? formatInchesPerHour(weather.rain_in_per_hr) : '—'}{' '}
              <RiskBadge level={risk.rain} />
            </dd>
          </div>
          <div>
            <dt>
              <Icon name="snow" size={13} />
              Snowfall
            </dt>
            <dd>
              {weather.snowfall_in_per_hr !== null ? formatInchesPerHour(weather.snowfall_in_per_hr) : '—'}{' '}
              <RiskBadge level={risk.snow} />
            </dd>
          </div>
        </dl>
      ) : (
        <div className="checkpoint-details__unavailable" role="note">
          <p className="checkpoint-details__unavailable-title">Weather unavailable: risk not assessed</p>
          <p>
            {weather.reason ? WEATHER_REASON_TEXT[weather.reason] : weather.message}
          </p>
          <p>This checkpoint is not treated as safe.</p>
        </div>
      )}

      {loadRule && (
        <p className="checkpoint-details__load-rule" role="note">
          <strong>Load rule:</strong> {loadRule}
        </p>
      )}
    </section>
  )
}

export default CheckpointDetails
