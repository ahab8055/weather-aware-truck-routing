import { describe, expect, it } from 'vitest'
import {
  defaultValues,
  departureTimeZoneHint,
  utcOffsetLabel,
  forecastHorizonWarning,
  parseDatetimeLocal,
  toIsoWithOffset,
  toRequest,
  validateTrip,
  type TripFormValues,
} from './tripForm'

// Tests run with TZ=America/Chicago (see vite.config.ts).
const valid: TripFormValues = {
  origin: 'Dallas, TX',
  destination: 'Houston, TX',
  departureLocal: '2026-10-19T08:00',
  loadWeightLbs: '42000',
  checkpointIntervalMiles: 25,
}

describe('validateTrip', () => {
  it('accepts a complete trip', () => {
    expect(validateTrip(valid)).toEqual({})
  })

  it('requires every field', () => {
    const errors = validateTrip({ ...valid, origin: ' ', destination: '', departureLocal: '', loadWeightLbs: '' })
    expect(Object.keys(errors).sort()).toEqual(['departureLocal', 'destination', 'loadWeightLbs', 'origin'])
  })

  it('rejects identical origin and destination', () => {
    expect(validateTrip({ ...valid, destination: ' dallas, tx ' }).destination).toMatch(/different/)
  })

  it('rejects overly long locations', () => {
    expect(validateTrip({ ...valid, origin: 'x'.repeat(201) }).origin).toMatch(/200/)
  })

  it.each(['0', '-5', '150001', 'abc', 'Infinity'])('rejects load weight %s', (load) => {
    expect(validateTrip({ ...valid, loadWeightLbs: load }).loadWeightLbs).toBeDefined()
  })

  it.each(['1', '80000', '150000', '42000.5'])('accepts load weight %s', (load) => {
    expect(validateTrip({ ...valid, loadWeightLbs: load }).loadWeightLbs).toBeUndefined()
  })

  it.each(['2026-02-30T08:00', '2026-10-19', 'tomorrow'])('rejects departure %s', (departure) => {
    expect(validateTrip({ ...valid, departureLocal: departure }).departureLocal).toBeDefined()
  })
})

describe('timezone-aware departure', () => {
  it('uses the local offset for daylight saving time', () => {
    expect(toRequest(valid).departure_time).toBe('2026-10-19T08:00:00-05:00')
  })

  it('uses the local offset for standard time', () => {
    expect(toRequest({ ...valid, departureLocal: '2026-01-15T08:00' }).departure_time).toBe(
      '2026-01-15T08:00:00-06:00',
    )
  })

  it('never formats local time as UTC', () => {
    const iso = toIsoWithOffset(new Date(2026, 9, 19, 8, 0))
    expect(iso.endsWith('Z')).toBe(false)
    expect(Date.parse(iso)).toBe(Date.UTC(2026, 9, 19, 13, 0))
  })

  it('builds the API request', () => {
    expect(toRequest({ ...valid, origin: ' Dallas, TX ', checkpointIntervalMiles: 50 })).toEqual({
      origin: 'Dallas, TX',
      destination: 'Houston, TX',
      departure_time: '2026-10-19T08:00:00-05:00',
      checkpoint_interval_miles: 50,
      load_weight_lbs: 42000,
    })
  })

  it('parses datetime-local values as local time', () => {
    expect(parseDatetimeLocal('2026-10-19T08:00')?.getHours()).toBe(8)
    expect(parseDatetimeLocal('bad')).toBeNull()
  })
})

describe('departure timezone hint', () => {
  it('names the timezone and the UTC offset for the chosen date', () => {
    expect(departureTimeZoneHint('2026-10-19T08:00', 'America/Chicago')).toBe(
      'Your local time (America/Chicago, UTC-05:00). Sent with this UTC offset.',
    )
    expect(departureTimeZoneHint('2026-01-15T08:00', 'America/Chicago')).toBe(
      'Your local time (America/Chicago, UTC-06:00). Sent with this UTC offset.',
    )
  })

  it('omits the offset until a valid date is entered', () => {
    expect(departureTimeZoneHint('', 'America/Chicago')).toBe(
      'Your local time (America/Chicago). Sent with this UTC offset.',
    )
  })

  it('formats offsets', () => {
    expect(utcOffsetLabel(new Date(2026, 9, 19, 8))).toBe('UTC-05:00')
  })
})

describe('defaults and warnings', () => {
  it('defaults departure to the next full hour', () => {
    const values = defaultValues(new Date(2026, 9, 18, 14, 25))
    expect(values.departureLocal).toBe('2026-10-18T15:00')
    expect(values.checkpointIntervalMiles).toBe(25)
  })

  it('warns when departure is beyond the forecast horizon', () => {
    const now = new Date(2026, 9, 18, 12, 0)
    expect(forecastHorizonWarning({ ...valid, departureLocal: '2026-11-10T08:00' }, now)).toMatch(/16 days/)
    expect(forecastHorizonWarning(valid, now)).toBeNull()
  })
})
