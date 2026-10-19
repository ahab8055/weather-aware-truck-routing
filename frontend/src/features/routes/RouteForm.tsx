import type { FormEvent } from 'react'
import Icon from '../../components/Icon'
import type { CheckpointIntervalMiles } from '../../types/routes'
import LocationAutocomplete from './LocationAutocomplete'
import {
  CHECKPOINT_INTERVALS,
  departureTimeZoneHint,
  MAX_LOAD_LBS,
  MIN_LOAD_LBS,
  type TripErrors,
  type TripField,
  type TripFormValues,
} from './tripForm'

interface RouteFormProps {
  values: TripFormValues
  errors: TripErrors
  loading: boolean
  timeZone: string
  horizonWarning: string | null
  onChange: <K extends TripField>(field: K, value: TripFormValues[K]) => void
  onSubmit: () => void
  onSwap: () => void
}

function fieldProps(field: TripField, errors: TripErrors) {
  const error = errors[field]
  return {
    id: field,
    name: field,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': error ? `${field}-error` : undefined,
  }
}

function FieldError({ field, errors }: { field: TripField; errors: TripErrors }) {
  const error = errors[field]
  if (!error) return null
  return (
    <p className="field__error" id={`${field}-error`}>
      {error}
    </p>
  )
}

function RouteForm({
  values,
  errors,
  loading,
  timeZone,
  horizonWarning,
  onChange,
  onSubmit,
  onSwap,
}: RouteFormProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!loading) onSubmit()
  }

  return (
    <form className="trip-form" onSubmit={handleSubmit} noValidate aria-label="Trip details">
      <div className="trip-form__endpoints">
        <div className="field">
          <label htmlFor="origin">
            <Icon name="pin" className="field__icon" />
            Origin
          </label>
          <LocationAutocomplete
            id="origin"
            placeholder="City, State or City, Country (e.g. Lahore, Pakistan)"
            value={values.origin}
            invalid={Boolean(errors.origin)}
            describedBy={errors.origin ? 'origin-error' : undefined}
            onChange={(value) => onChange('origin', value)}
          />
          <FieldError field="origin" errors={errors} />
        </div>

        <button
          type="button"
          className="swap-button"
          aria-label="Swap origin and destination"
          title="Swap origin and destination"
          onClick={onSwap}
        >
          <Icon name="swap" />
        </button>

        <div className="field">
          <label htmlFor="destination">
            <Icon name="flag" className="field__icon" />
            Destination
          </label>
          <LocationAutocomplete
            id="destination"
            placeholder="e.g. Islamabad, Pakistan or Houston, TX"
            value={values.destination}
            invalid={Boolean(errors.destination)}
            describedBy={errors.destination ? 'destination-error' : undefined}
            onChange={(value) => onChange('destination', value)}
          />
          <FieldError field="destination" errors={errors} />
        </div>
      </div>

      <div className="trip-form__row">
        <div className="field">
          <label htmlFor="departureLocal">
            <Icon name="clock" className="field__icon" />
            Departure
          </label>
          <input
            {...fieldProps('departureLocal', errors)}
            type="datetime-local"
            value={values.departureLocal}
            onChange={(event) => onChange('departureLocal', event.target.value)}
          />
          <p className="field__hint" id="departureLocal-hint">
            {departureTimeZoneHint(values.departureLocal, timeZone)}
          </p>
          <FieldError field="departureLocal" errors={errors} />
        </div>

        <div className="field">
          <label htmlFor="loadWeightLbs">
            <Icon name="weight" className="field__icon" />
            Truck + load weight (lb)
          </label>
          <input
            {...fieldProps('loadWeightLbs', errors)}
            type="number"
            inputMode="numeric"
            min={MIN_LOAD_LBS}
            max={MAX_LOAD_LBS}
            step="any"
            placeholder="e.g. 42000"
            value={values.loadWeightLbs}
            onChange={(event) => onChange('loadWeightLbs', event.target.value)}
          />
          <FieldError field="loadWeightLbs" errors={errors} />
        </div>
      </div>

      <fieldset
        className="field interval-group"
        aria-describedby={errors.checkpointIntervalMiles ? 'checkpointIntervalMiles-error' : undefined}
      >
        <legend>
          <Icon name="gauge" className="field__icon" />
          Weather checkpoint every
        </legend>
        <div className="interval-group__options">
          {CHECKPOINT_INTERVALS.map((interval) => (
            <label key={interval} className="interval-option">
              <input
                type="radio"
                name="checkpointIntervalMiles"
                value={interval}
                checked={values.checkpointIntervalMiles === interval}
                onChange={() => onChange('checkpointIntervalMiles', interval as CheckpointIntervalMiles)}
              />
              <span>{interval} mi</span>
            </label>
          ))}
        </div>
        <FieldError field="checkpointIntervalMiles" errors={errors} />
      </fieldset>

      {horizonWarning && (
        <p className="trip-form__warning" role="note">
          {horizonWarning}
        </p>
      )}

      <button className="button button--primary" type="submit" disabled={loading}>
        {loading && <span className="spinner" aria-hidden="true" />}
        {loading ? 'Evaluating routes…' : 'Evaluate routes'}
      </button>
    </form>
  )
}

export default RouteForm
