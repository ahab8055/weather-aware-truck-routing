import { useEffect, useRef, useState } from 'react'
import { formatLocalDateTime } from './format'
import { FORECAST_STEP_HOURS, FORECAST_WINDOW_HOURS, selectedTime } from './heatmap'
import { RISK_COLORS, RISK_LABELS, type CheckpointRiskState } from './riskDisplay'

const TICKS = [0, 12, 24, 36, 48]
const PLAY_INTERVAL_MS = 700

interface ForecastSliderProps {
  departureIso: string
  offsetHours: number
  /** Forecast hour actually used for this slot, or null when none is available. */
  forecastTime: string | null
  onChange: (offsetHours: number) => void
  /** Worst risk along the route per hour (index = offset), drawn above the slider. */
  timeline?: CheckpointRiskState[] | null
}

function tickLabel(hours: number): string {
  return hours === 0 ? 'Departure' : `+${hours} h`
}

function clampHour(hours: number): number {
  return Math.min(FORECAST_WINDOW_HOURS, Math.max(0, hours))
}

function ForecastSlider({ departureIso, offsetHours, forecastTime, onChange, timeline = null }: ForecastSliderProps) {
  const when = formatLocalDateTime(selectedTime(departureIso, offsetHours).toISOString())
  const [playing, setPlaying] = useState(false)
  // Latest values for the interval callback, which outlives a single render.
  const offsetRef = useRef(offsetHours)
  const onChangeRef = useRef(onChange)
  useEffect(() => {
    offsetRef.current = offsetHours
    onChangeRef.current = onChange
  })

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => {
      const next = offsetRef.current + FORECAST_STEP_HOURS
      if (next > FORECAST_WINDOW_HOURS) {
        setPlaying(false)
        return
      }
      onChangeRef.current(next)
    }, PLAY_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [playing])

  function togglePlay() {
    // Restart from departure when play is pressed at the end of the window.
    if (!playing && offsetHours >= FORECAST_WINDOW_HOURS) onChange(0)
    setPlaying((current) => !current)
  }

  function step(delta: number) {
    setPlaying(false)
    onChange(clampHour(offsetHours + delta))
  }

  return (
    <div className="forecast-slider">
      <div className="forecast-slider__top">
        <p className="forecast-slider__readout" aria-live="polite">
          <strong>+{offsetHours} h</strong> · {when}
        </p>
        <div className="forecast-slider__controls">
          <button
            type="button"
            className="icon-button"
            aria-label="Previous hour"
            disabled={offsetHours <= 0}
            onClick={() => step(-FORECAST_STEP_HOURS)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M15 6l-6 6 6 6" />
            </svg>
          </button>
          <button
            type="button"
            className="icon-button icon-button--primary"
            aria-label={playing ? 'Pause forecast' : 'Play forecast'}
            aria-pressed={playing}
            onClick={togglePlay}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              {playing ? <path d="M9 6v12M15 6v12" /> : <path d="M8 5l11 7-11 7z" className="fill" />}
            </svg>
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="Next hour"
            disabled={offsetHours >= FORECAST_WINDOW_HOURS}
            onClick={() => step(FORECAST_STEP_HOURS)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
        </div>
      </div>

      <label htmlFor="forecast-offset">Forecast time (hours after departure)</label>
      {timeline && timeline.length > 0 && (
        // Mouse shortcut only; the slider below is the accessible control.
        <div className="forecast-timeline" aria-hidden="true" data-testid="forecast-timeline">
          {timeline.map((state, hour) => (
            <span
              key={hour}
              className={`forecast-timeline__slot forecast-timeline__slot--${state}${hour === offsetHours ? ' forecast-timeline__slot--current' : ''}`}
              style={{ backgroundColor: state === 'unavailable' ? undefined : RISK_COLORS[state] }}
              title={`+${hour} h: ${RISK_LABELS[state]}`}
              onClick={() => {
                setPlaying(false)
                onChange(hour)
              }}
            />
          ))}
        </div>
      )}
      <input
        id="forecast-offset"
        type="range"
        min={0}
        max={FORECAST_WINDOW_HOURS}
        step={FORECAST_STEP_HOURS}
        value={offsetHours}
        aria-valuetext={`+${offsetHours} h, ${when}`}
        list="forecast-offset-ticks"
        onChange={(event) => {
          setPlaying(false)
          onChange(Number(event.target.value))
        }}
      />
      <datalist id="forecast-offset-ticks">
        {TICKS.map((tick) => (
          <option key={tick} value={tick} label={tickLabel(tick)} />
        ))}
      </datalist>
      <div className="forecast-slider__ticks" aria-hidden="true">
        {TICKS.map((tick) => (
          <span key={tick}>{tickLabel(tick)}</span>
        ))}
      </div>
      <p className="forecast-slider__used">
        Forecast hour used:{' '}
        {forecastTime ? formatLocalDateTime(forecastTime) : 'no forecast available for this hour'}
      </p>
    </div>
  )
}

export default ForecastSlider
