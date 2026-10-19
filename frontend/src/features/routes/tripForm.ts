import type { CheckpointIntervalMiles, RouteCandidatesRequest } from '../../types/routes'

export const CHECKPOINT_INTERVALS: readonly CheckpointIntervalMiles[] = [10, 25, 50]
export const MAX_LOCATION_LENGTH = 200
export const MIN_LOAD_LBS = 1
export const MAX_LOAD_LBS = 150_000
export const FORECAST_HORIZON_DAYS = 16

export interface TripFormValues {
  origin: string
  destination: string
  /** Value of a `datetime-local` input: local wall-clock time, no offset. */
  departureLocal: string
  loadWeightLbs: string
  checkpointIntervalMiles: CheckpointIntervalMiles
}

export type TripField = keyof TripFormValues
export type TripErrors = Partial<Record<TripField, string>>

const pad = (value: number) => String(value).padStart(2, '0')

function toDatetimeLocal(date: Date): string {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

export function defaultValues(now: Date = new Date()): TripFormValues {
  const nextHour = new Date(now)
  nextHour.setHours(now.getHours() + 1, 0, 0, 0)
  return {
    origin: '',
    destination: '',
    departureLocal: toDatetimeLocal(nextHour),
    loadWeightLbs: '',
    checkpointIntervalMiles: 25,
  }
}

const DATETIME_LOCAL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/

/** Parse a `datetime-local` value as local time; null if malformed or nonexistent. */
export function parseDatetimeLocal(value: string): Date | null {
  const match = DATETIME_LOCAL.exec(value)
  if (!match) return null
  const [year, month, day, hour, minute] = match.slice(1).map(Number)
  const date = new Date(year, month - 1, day, hour, minute)
  // Reject impossible dates (e.g. Feb 30) that Date would silently roll over.
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null
  }
  return date
}

/**
 * ISO 8601 with the browser's UTC offset for that instant (DST-aware), e.g.
 * "2026-10-19T08:00:00-05:00". Local times are never sent as UTC.
 */
export function toIsoWithOffset(date: Date): string {
  const offsetMinutes = -date.getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const absolute = Math.abs(offsetMinutes)
  return (
    `${toDatetimeLocal(date)}:00` +
    `${sign}${pad(Math.floor(absolute / 60))}:${pad(absolute % 60)}`
  )
}

/** "UTC+05:00"-style offset of the browser's timezone at `date` (DST-aware). */
export function utcOffsetLabel(date: Date): string {
  return `UTC${toIsoWithOffset(date).slice(-6)}`
}

/** Human-readable description of the timezone the departure is entered and sent in. */
export function departureTimeZoneHint(departureLocal: string, timeZone: string = localTimeZoneName()): string {
  const departure = parseDatetimeLocal(departureLocal)
  const offset = departure ? `, ${utcOffsetLabel(departure)}` : ''
  return `Your local time (${timeZone}${offset}). Sent with this UTC offset.`
}

export function localTimeZoneName(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

export function validateTrip(values: TripFormValues): TripErrors {
  const errors: TripErrors = {}
  const origin = values.origin.trim()
  const destination = values.destination.trim()

  if (!origin) errors.origin = 'Enter where the trip starts.'
  else if (origin.length > MAX_LOCATION_LENGTH) errors.origin = `Use at most ${MAX_LOCATION_LENGTH} characters.`

  if (!destination) errors.destination = 'Enter where the trip ends.'
  else if (destination.length > MAX_LOCATION_LENGTH) {
    errors.destination = `Use at most ${MAX_LOCATION_LENGTH} characters.`
  } else if (origin && origin.toLowerCase() === destination.toLowerCase()) {
    errors.destination = 'Destination must be different from the origin.'
  }

  if (!values.departureLocal) errors.departureLocal = 'Choose a departure date and time.'
  else if (!parseDatetimeLocal(values.departureLocal)) errors.departureLocal = 'Enter a valid date and time.'

  const load = values.loadWeightLbs.trim()
  const loadNumber = Number(load)
  if (!load) errors.loadWeightLbs = 'Enter the truck and load weight.'
  else if (!Number.isFinite(loadNumber)) errors.loadWeightLbs = 'Enter a number of pounds.'
  else if (loadNumber < MIN_LOAD_LBS || loadNumber > MAX_LOAD_LBS) {
    errors.loadWeightLbs = `Enter a weight between ${MIN_LOAD_LBS} and ${MAX_LOAD_LBS.toLocaleString('en-US')} lb.`
  }

  if (!CHECKPOINT_INTERVALS.includes(values.checkpointIntervalMiles)) {
    errors.checkpointIntervalMiles = 'Choose 10, 25 or 50 miles.'
  }
  return errors
}

/** Build the API request. Call only after `validateTrip` returned no errors. */
export function toRequest(values: TripFormValues): RouteCandidatesRequest {
  const departure = parseDatetimeLocal(values.departureLocal)
  if (!departure) throw new Error('Invalid departure time')
  return {
    origin: values.origin.trim(),
    destination: values.destination.trim(),
    departure_time: toIsoWithOffset(departure),
    checkpoint_interval_miles: values.checkpointIntervalMiles,
    load_weight_lbs: Number(values.loadWeightLbs),
  }
}

/** Soft warning (does not block submission) for departures beyond the forecast horizon. */
export function forecastHorizonWarning(values: TripFormValues, now: Date = new Date()): string | null {
  const departure = parseDatetimeLocal(values.departureLocal)
  if (!departure) return null
  const days = (departure.getTime() - now.getTime()) / 86_400_000
  if (days > FORECAST_HORIZON_DAYS) {
    return `Weather forecasts cover about ${FORECAST_HORIZON_DAYS} days ahead; this trip will not get a weather evaluation.`
  }
  return null
}

/** Map backend field names to form fields. */
export const SERVER_FIELD_MAP: Record<string, TripField> = {
  origin: 'origin',
  destination: 'destination',
  departure_time: 'departureLocal',
  load_weight_lbs: 'loadWeightLbs',
  checkpoint_interval_miles: 'checkpointIntervalMiles',
}
