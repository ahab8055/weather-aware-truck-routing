import { useEffect, useMemo, useRef, useState } from 'react'
import { evaluateRoutes, getForecastWindow } from '../../api/client'
import Icon from '../../components/Icon'
import type { RouteEvaluationResponse } from '../../types/routes'
import CheckpointDetails from './CheckpointDetails'
import CheckpointList from './CheckpointList'
import ForecastHeatmapPanel, { type ForecastState } from './ForecastHeatmapPanel'
import RouteComparison from './RouteComparison'
import RouteForm from './RouteForm'
import RouteMap from './RouteMap'
import RouteSkeleton from './RouteSkeleton'
import { EvaluationBanners, FailureBanner } from './ResultBanner'
import { toPlannerFailure, type PlannerFailure } from './apiErrors'
import {
  MAX_HEATMAP_LOCATIONS,
  corridorSegments,
  observationsAt,
  etaOffsetHours,
  uniqueCheckpointLocations,
  worstStateByHour,
} from './heatmap'
import {
  SERVER_FIELD_MAP,
  defaultValues,
  forecastHorizonWarning,
  localTimeZoneName,
  toRequest,
  validateTrip,
  type TripErrors,
  type TripField,
  type TripFormValues,
} from './tripForm'

export const REQUEST_TIMEOUT_MS = 90_000
export const FORECAST_TIMEOUT_MS = 60_000

type RequestState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'failed'; failure: PlannerFailure }
  | { status: 'done'; response: RouteEvaluationResponse }

const NOT_ROUTABLE_FIELD_ERROR = 'Not near a road trucks can use. Try a city or street address.'

function serverFieldErrors(failure: PlannerFailure | null): TripErrors {
  if (failure?.kind === 'routing' && failure.code === 'location_not_routable' && failure.field) {
    return { [failure.field]: NOT_ROUTABLE_FIELD_ERROR }
  }
  if (failure?.kind !== 'validation') return {}
  const errors: TripErrors = {}
  for (const [field, message] of Object.entries(failure.fieldErrors)) {
    const formField = SERVER_FIELD_MAP[field]
    if (formField && message) errors[formField] = message
  }
  return errors
}

function candidateField(failure: PlannerFailure, values: TripFormValues): 'origin' | 'destination' | null {
  if (failure.kind !== 'routing' || !failure.query) return null
  const query = failure.query.trim().toLowerCase()
  if (values.origin.trim().toLowerCase() === query) return 'origin'
  if (values.destination.trim().toLowerCase() === query) return 'destination'
  return null
}

function RoutePlanner() {
  const [values, setValues] = useState<TripFormValues>(() => defaultValues())
  const [clientErrors, setClientErrors] = useState<TripErrors>({})
  const [state, setState] = useState<RequestState>({ status: 'idle' })
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const [selectedCheckpoint, setSelectedCheckpoint] = useState(0)
  const controllerRef = useRef<AbortController | null>(null)
  const [heatmapEnabled, setHeatmapEnabled] = useState(false)
  const [offsetHours, setOffsetHours] = useState(0)
  const [forecast, setForecast] = useState<ForecastState>({ status: 'idle' })
  const forecastControllerRef = useRef<AbortController | null>(null)

  useEffect(
    () => () => {
      controllerRef.current?.abort()
      forecastControllerRef.current?.abort()
    },
    [],
  )

  function handleChange<K extends TripField>(field: K, value: TripFormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }))
    setClientErrors((current) => ({ ...current, [field]: undefined }))
  }

  function handleSwap() {
    setValues((current) => ({ ...current, origin: current.destination, destination: current.origin }))
    setClientErrors((current) => ({ ...current, origin: undefined, destination: undefined }))
  }

  async function handleSubmit() {
    const errors = validateTrip(values)
    setClientErrors(errors)
    if (Object.keys(errors).length > 0) return

    controllerRef.current?.abort()
    forecastControllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(REQUEST_TIMEOUT_MS)])

    setState({ status: 'loading' })
    try {
      const response = await evaluateRoutes(toRequest(values), signal)
      if (controller.signal.aborted) return
      setState({ status: 'done', response })
      setSelectedRouteId(response.recommended_route_id ?? response.routes[0]?.id ?? null)
      setSelectedCheckpoint(0)
      setOffsetHours(0)
      setForecast({ status: 'idle' })
      if (heatmapEnabled) void loadForecast(response)
    } catch (error) {
      // A newer request (or unmount) superseded this one.
      if (controller.signal.aborted) return
      setState({ status: 'failed', failure: toPlannerFailure(error) })
    }
  }

  /** Fetch the 0–48 h window once per evaluation; slider moves reuse it. */
  async function loadForecast(evaluation: RouteEvaluationResponse) {
    forecastControllerRef.current?.abort()
    const { locations } = uniqueCheckpointLocations(evaluation.routes)
    if (locations.length === 0) {
      setForecast({ status: 'failed', message: 'There are no checkpoints to show.' })
      return
    }
    if (locations.length > MAX_HEATMAP_LOCATIONS) {
      setForecast({
        status: 'failed',
        message: `These routes have ${locations.length} checkpoints; the heatmap supports up to ${MAX_HEATMAP_LOCATIONS}. Choose a larger checkpoint interval.`,
      })
      return
    }
    const controller = new AbortController()
    forecastControllerRef.current = controller
    setForecast({ status: 'loading' })
    try {
      const forecastWindow = await getForecastWindow(
        {
          locations,
          departure_time: evaluation.departure_time,
          load_weight_lbs: evaluation.load_weight_lbs,
        },
        AbortSignal.any([controller.signal, AbortSignal.timeout(FORECAST_TIMEOUT_MS)]),
      )
      if (controller.signal.aborted) return
      setForecast({ status: 'done', window: forecastWindow })
    } catch (error) {
      // Superseded by a newer evaluation or unmount: ignore.
      if (controller.signal.aborted) return
      setForecast({ status: 'failed', message: toPlannerFailure(error).message })
    }
  }

  function handleToggleHeatmap(enabled: boolean) {
    setHeatmapEnabled(enabled)
    if (enabled && response && forecast.status === 'idle') void loadForecast(response)
  }

  function handleShowAtEta(offset: number) {
    setOffsetHours(offset)
    if (!heatmapEnabled) handleToggleHeatmap(true)
  }

  function handleSelectRoute(routeId: string) {
    setSelectedRouteId(routeId)
    setSelectedCheckpoint(0)
  }

  const failure = state.status === 'failed' ? state.failure : null
  const response = state.status === 'done' ? state.response : null
  const selectedRoute =
    response?.routes.find((route) => route.id === selectedRouteId) ?? response?.routes[0] ?? null
  const checkpoint =
    selectedRoute?.checkpoints.find((c) => c.index === selectedCheckpoint) ??
    selectedRoute?.checkpoints[0] ??
    null
  const pickField = failure ? candidateField(failure, values) : null
  const etaOffset = response && checkpoint ? etaOffsetHours(response.departure_time, checkpoint.eta) : null

  const heatmapLocations = useMemo(
    () => (response ? uniqueCheckpointLocations(response.routes) : null),
    [response],
  )
  const heatmapPoints =
    heatmapEnabled && forecast.status === 'done' && selectedRoute && heatmapLocations
      ? observationsAt(forecast.window, heatmapLocations.indexByKey, selectedRoute, offsetHours)
      : null
  const heatmapTimeline = useMemo(
    () =>
      heatmapEnabled && forecast.status === 'done' && selectedRoute && heatmapLocations
        ? worstStateByHour(forecast.window, heatmapLocations.indexByKey, selectedRoute)
        : null,
    [heatmapEnabled, forecast, selectedRoute, heatmapLocations],
  )
  const heatmapSegments =
    heatmapPoints && selectedRoute
      ? corridorSegments(
          selectedRoute,
          heatmapPoints.map((point) => point.state),
        )
      : null

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-[420px_minmax(0,1fr)]">
      <aside
        className="flex min-w-0 flex-col gap-4 border-white/10 bg-navy-900 p-4 lg:overflow-y-auto lg:border-r"
        aria-label="Trip planning"
      >
        <section className="panel" aria-labelledby="trip-heading">
          <h2 id="trip-heading">Plan a trip</h2>
          <RouteForm
            values={values}
            errors={{ ...serverFieldErrors(failure), ...stripEmpty(clientErrors) }}
            loading={state.status === 'loading'}
            timeZone={localTimeZoneName()}
            horizonWarning={forecastHorizonWarning(values)}
            onChange={handleChange}
            onSubmit={handleSubmit}
            onSwap={handleSwap}
          />
        </section>

        <div aria-live="polite">
          {state.status === 'loading' && (
            <p className="banner banner--info" role="status">
              Finding routes and checking the forecast along each one…
            </p>
          )}
          {failure && (
            <FailureBanner
              failure={failure}
              candidateField={pickField}
              onPickCandidate={(candidate) => pickField && handleChange(pickField, candidate)}
            />
          )}
          {response && <EvaluationBanners response={response} />}
        </div>

        {state.status === 'loading' && <RouteSkeleton />}

        {response && response.routes.length > 0 && (
          <RouteComparison
            response={response}
            selectedRouteId={selectedRoute?.id ?? null}
            onSelectRoute={handleSelectRoute}
          />
        )}
      </aside>

      <section className="flex min-h-0 min-w-0 flex-col" aria-label="Route results">
        {response && selectedRoute ? (
          <>
            <div className="relative flex flex-col lg:min-h-0 lg:flex-1">
              <div className="h-[380px] lg:h-full">
                <RouteMap
                  routes={response.routes}
                  origin={response.origin}
                  destination={response.destination}
                  selectedRouteId={selectedRoute.id}
                  selectedCheckpointIndex={checkpoint?.index ?? 0}
                  onSelectRoute={handleSelectRoute}
                  onSelectCheckpoint={setSelectedCheckpoint}
                  heatmap={heatmapSegments}
                />
              </div>
              <div className="panel m-3 lg:absolute lg:top-0 lg:right-0 lg:z-[1000] lg:max-h-[calc(100%-1.5rem)] lg:w-[360px] lg:overflow-y-auto lg:border-white/15 lg:bg-navy-900/90 lg:shadow-2xl lg:shadow-black/50 lg:backdrop-blur-md">
                <ForecastHeatmapPanel
                  enabled={heatmapEnabled}
                  onToggle={handleToggleHeatmap}
                  forecast={forecast}
                  onRetry={() => void loadForecast(response)}
                  departureIso={response.departure_time}
                  offsetHours={offsetHours}
                  onOffsetChange={setOffsetHours}
                  routeLabel={`Route ${selectedRoute.provider_order + 1}`}
                  points={heatmapPoints}
                  timeline={heatmapTimeline}
                />
              </div>
            </div>
            <div className="grid gap-3 border-t border-white/10 bg-navy-900 p-3 md:grid-cols-2 lg:max-h-[38vh] lg:overflow-y-auto">
              {checkpoint && (
                <div className="panel">
                  <CheckpointDetails
                    checkpoint={checkpoint}
                    routeLabel={`Route ${selectedRoute.provider_order + 1}`}
                    etaOffsetHours={etaOffset}
                    onShowAtEta={etaOffset === null ? undefined : () => handleShowAtEta(etaOffset)}
                  />
                </div>
              )}
              <div className="panel">
                <CheckpointList
                  route={selectedRoute}
                  selectedIndex={checkpoint?.index ?? 0}
                  onSelect={setSelectedCheckpoint}
                />
              </div>
            </div>
          </>
        ) : (
          <EmptyStage loading={state.status === 'loading'} />
        )}
      </section>
    </div>
  )
}

const STEPS = [
  { icon: 'pin', text: 'Enter origin, destination, departure and load weight.' },
  { icon: 'route', text: 'We fetch truck routes and check the forecast at each checkpoint.' },
  { icon: 'check', text: 'Pick the safest route; inspect any checkpoint on the map.' },
] as const

function EmptyStage({ loading }: { loading: boolean }) {
  return (
    <div className="relative grid min-h-[380px] flex-1 place-items-center overflow-hidden bg-navy-950 p-6">
      {/* Faint route grid backdrop */}
      <div
        className="pointer-events-none absolute inset-0 opacity-40 [background-image:linear-gradient(rgb(255_255_255/4%)_1px,transparent_1px),linear-gradient(90deg,rgb(255_255_255/4%)_1px,transparent_1px)] [background-size:40px_40px]"
        aria-hidden="true"
      />
      {loading && <div className="skeleton absolute inset-0 rounded-none opacity-60" aria-hidden="true" />}
      <div className="relative grid max-w-md justify-items-center gap-4 text-center">
        <span
          className={`grid size-16 place-items-center rounded-2xl border border-brand-400/30 bg-brand-400/10 text-brand-400${loading ? ' animate-pulse' : ''}`}
          aria-hidden="true"
        >
          <Icon name="truck" size={30} />
        </span>
        <h2 className="m-0 text-xl text-white">{loading ? 'Evaluating…' : 'No routes yet'}</h2>
        <p className="m-0 text-slate-400">
          Enter an origin, destination, departure time and load. Routes appear here with weather
          risk checked at each checkpoint along the way.
        </p>
        {!loading && (
          <ol className="m-0 grid list-none gap-2 p-0 text-left text-sm text-slate-300">
            {STEPS.map((step, i) => (
              <li key={step.icon} className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand-400/15 text-xs font-bold text-brand-300">
                  {i + 1}
                </span>
                <Icon name={step.icon} className="shrink-0 text-brand-400" />
                {step.text}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

function stripEmpty(errors: TripErrors): TripErrors {
  return Object.fromEntries(Object.entries(errors).filter(([, message]) => message)) as TripErrors
}

export default RoutePlanner
