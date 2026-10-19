import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, evaluateRoutes } from '../../api/client'
import type { RouteEvaluationResponse } from '../../types/routes'
import {
  allUnsafeEvaluation,
  evaluation,
  partialEvaluation,
  safeEvaluation,
} from '../../test/fixtures'
import RoutePlanner from './RoutePlanner'
import type { RouteMapProps } from './RouteMap'

vi.mock('../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/client')>()
  return {
    ...actual,
    evaluateRoutes: vi.fn(),
    getLocationSuggestions: vi.fn().mockResolvedValue({ query: '', suggestions: [] }),
  }
})

// Leaflet needs real layout; a stub exposes the same props so selection sync is testable.
vi.mock('./RouteMap', () => ({
  default: (props: RouteMapProps) => {
    const selected = props.routes.find((r) => r.id === props.selectedRouteId)
    return (
      <div data-testid="route-map" data-selected-route={props.selectedRouteId} data-selected-checkpoint={props.selectedCheckpointIndex}>
        {props.routes.map((r) => (
          <button key={r.id} type="button" onClick={() => props.onSelectRoute(r.id)}>
            map line {r.id}
          </button>
        ))}
        {selected?.checkpoints.map((c) => (
          <button key={c.index} type="button" onClick={() => props.onSelectCheckpoint(c.index)}>
            map marker {c.index}
          </button>
        ))}
      </div>
    )
  },
}))

const evaluateMock = vi.mocked(evaluateRoutes)

async function fillValidTrip() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Origin'), 'Waco, TX')
  await user.type(screen.getByLabelText('Destination'), 'Temple, TX')
  fireEvent.change(screen.getByLabelText('Departure'), { target: { value: '2026-10-19T08:00' } })
  await user.type(screen.getByLabelText('Truck + load weight (lb)'), '42000')
  return user
}

async function submitWith(response: RouteEvaluationResponse) {
  evaluateMock.mockResolvedValueOnce(response)
  render(<RoutePlanner />)
  const user = await fillValidTrip()
  await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))
  return user
}

function routeCard(name: string) {
  return screen.getByText(name, { selector: '.route-card__title' }).closest('button') as HTMLButtonElement
}

beforeEach(() => {
  evaluateMock.mockReset()
})

describe('RoutePlanner', () => {
  it('shows an empty state before the first evaluation', () => {
    render(<RoutePlanner />)

    expect(screen.getByText('No routes yet')).toBeInTheDocument()
    expect(screen.queryByTestId('route-map')).not.toBeInTheDocument()
  })

  it('blocks submission and shows field errors for invalid input', async () => {
    render(<RoutePlanner />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))

    expect(evaluateMock).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Origin')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Enter where the trip starts.')).toBeInTheDocument()
    expect(screen.getByText('Enter the truck and load weight.')).toBeInTheDocument()
  })

  it('sends a timezone-aware request and disables the button while loading', async () => {
    let resolve: (value: RouteEvaluationResponse) => void = () => {}
    evaluateMock.mockReturnValueOnce(new Promise((r) => (resolve = r)))
    render(<RoutePlanner />)
    const user = await fillValidTrip()

    await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))

    const button = screen.getByRole('button', { name: 'Evaluating routes…' })
    expect(button).toBeDisabled()
    expect(screen.getByText(/Finding routes and checking the forecast/)).toBeInTheDocument()
    expect(screen.getByTestId('route-skeleton')).toBeInTheDocument()
    expect(evaluateMock).toHaveBeenCalledTimes(1)
    expect(evaluateMock.mock.calls[0][0]).toEqual({
      origin: 'Waco, TX',
      destination: 'Temple, TX',
      departure_time: '2026-10-19T08:00:00-05:00',
      checkpoint_interval_miles: 25,
      load_weight_lbs: 42000,
    })
    expect(evaluateMock.mock.calls[0][1]).toBeInstanceOf(AbortSignal)

    resolve(safeEvaluation())
    expect(await screen.findByText('Recommended: Route 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Evaluate routes' })).toBeEnabled()
    expect(screen.queryByTestId('route-skeleton')).not.toBeInTheDocument()
  })

  it('swaps origin and destination', async () => {
    render(<RoutePlanner />)
    const user = await fillValidTrip()

    await user.click(screen.getByRole('button', { name: 'Swap origin and destination' }))

    expect(screen.getByLabelText('Origin')).toHaveValue('Temple, TX')
    expect(screen.getByLabelText('Destination')).toHaveValue('Waco, TX')
  })

  it('renders a successful evaluation with the recommended route selected', async () => {
    await submitWith(safeEvaluation())

    expect(await screen.findByText('Recommended: Route 2')).toBeInTheDocument()
    expect(screen.getByText('Recommended route: route-2.')).toBeInTheDocument()
    expect(screen.getByTestId('route-map')).toHaveAttribute('data-selected-route', 'route-2')
    expect(routeCard('Route 2')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Route 2 checkpoints (4)')).toBeInTheDocument()
  })

  it('keeps map, cards and checkpoint list in sync when selecting routes and checkpoints', async () => {
    const user = await submitWith(safeEvaluation())
    await screen.findByText('Recommended: Route 2')

    await user.click(routeCard('Route 1'))
    expect(screen.getByTestId('route-map')).toHaveAttribute('data-selected-route', 'route-1')
    expect(screen.getByText('Route 1 checkpoints (4)')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'map marker 1' }))
    const details = screen.getByRole('region', { name: 'Checkpoint details' })
    expect(within(details).getByText('Route 1 · Checkpoint #1')).toBeInTheDocument()
    expect(within(details).getByText('47.0 mph')).toBeInTheDocument()
    expect(within(details).getByText('Overall: Severe')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'map line route-2' }))
    expect(routeCard('Route 2')).toHaveAttribute('aria-pressed', 'true')
    expect(within(screen.getByRole('region', { name: 'Checkpoint details' })).getByText('Route 2 · Checkpoint #0')).toBeInTheDocument()
  })

  it('selects checkpoints from the keyboard-accessible list', async () => {
    const user = await submitWith(safeEvaluation())
    await screen.findByText('Recommended: Route 2')
    await user.click(routeCard('Route 1'))

    const list = screen.getByRole('region', { name: 'Route 1 checkpoints (4)' })
    await user.click(within(list).getAllByRole('button')[2])

    expect(screen.getByTestId('route-map')).toHaveAttribute('data-selected-checkpoint', '2')
    expect(screen.getByText('Route 1 · Checkpoint #2')).toBeInTheDocument()
  })

  it('explains when every route is unsafe without recommending one', async () => {
    await submitWith(allUnsafeEvaluation())

    expect(await screen.findByText('No safe route available')).toBeInTheDocument()
    expect(
      screen.getByText('No safe route available: every candidate route contains No Travel conditions.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
    expect(screen.queryByText(/Evaluation failed/)).not.toBeInTheDocument()
  })

  it('warns that the comparison is inconclusive when a route lacks weather', async () => {
    const user = await submitWith(partialEvaluation())

    expect(await screen.findByText('Route comparison may be inconclusive')).toBeInTheDocument()
    expect(
      screen.getByText('Provisional: Route 1 is the safest of the fully evaluated routes'),
    ).toBeInTheDocument()
    expect(screen.getByText(/overall comparison is inconclusive/)).toBeInTheDocument()
    expect(screen.queryByText(/^Recommended: /)).not.toBeInTheDocument()
    expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
    expect(within(routeCard('Route 1')).getByText('Provisional pick')).toBeInTheDocument()
    expect(screen.getByText('Partial weather coverage')).toBeInTheDocument()

    await user.click(routeCard('Route 2'))
    expect(within(routeCard('Route 2')).getByText('Not fully evaluated')).toBeInTheDocument()
    const list = screen.getByRole('region', { name: 'Route 2 checkpoints (4)' })
    expect(within(list).getAllByText('Weather unavailable')).toHaveLength(2)
    expect(within(list).getAllByText('Low')).toHaveLength(2)

    await user.click(within(list).getAllByRole('button')[3])
    const details = screen.getByRole('region', { name: 'Checkpoint details' })
    expect(within(details).getByText('Overall: Weather unavailable')).toBeInTheDocument()
    expect(within(details).queryByText(/Low/)).not.toBeInTheDocument()
  })

  it('reports an inconclusive result when no fully evaluated route is safe', async () => {
    const partial = partialEvaluation()
    await submitWith({
      ...partial,
      routes: [partial.routes[1]],
      route_count: 1,
      recommended_route_id: null,
      safe_route_available: false,
      recommendation_status: 'inconclusive',
      comparison_conclusive: false,
      ranking: [],
      recommendation_message:
        'No safe route can be confirmed: weather forecasts are unavailable for 1 of 1 route(s).',
    })

    expect(await screen.findByText('No safe route can be confirmed')).toBeInTheDocument()
    expect(screen.queryByText('No safe route available')).not.toBeInTheDocument()
    expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
    expect(screen.queryByText('Provisional pick')).not.toBeInTheDocument()
    expect(within(routeCard('Route 2')).getByText('Not fully evaluated')).toBeInTheDocument()
  })

  it('handles a response without routes', async () => {
    await submitWith(evaluation({ recommendation_message: 'No safe route available.' }))

    expect(await screen.findByText('No routes were returned for this trip.')).toBeInTheDocument()
    expect(screen.queryByTestId('route-map')).not.toBeInTheDocument()
  })

  it('shows server field errors and keeps entered values', async () => {
    evaluateMock.mockRejectedValueOnce(
      new ApiError(400, 'bad', { departure_time: ['Include a timezone offset.'] }),
    )
    render(<RoutePlanner />)
    const user = await fillValidTrip()

    await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))

    expect(await screen.findByText('Evaluation failed: Check the trip details')).toBeInTheDocument()
    expect(screen.getByText('Include a timezone offset.')).toBeInTheDocument()
    expect(screen.getByLabelText('Origin')).toHaveValue('Waco, TX')
    expect(screen.getByLabelText('Truck + load weight (lb)')).toHaveValue(42000)
  })

  it('points at the input whose location is not near a truck road', async () => {
    evaluateMock.mockRejectedValueOnce(
      new ApiError(422, 'x', {
        error: {
          code: 'location_not_routable',
          message: 'The destination "Temple, TX" is not near a road trucks can use.',
          query: 'Temple, TX',
          field: 'destination',
        },
      }),
    )
    render(<RoutePlanner />)
    const user = await fillValidTrip()
    await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))

    expect(await screen.findByText('Evaluation failed: Location is not near a truck road')).toBeInTheDocument()
    expect(screen.getByLabelText('Destination')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Not near a road trucks can use. Try a city or street address.')).toBeInTheDocument()
    expect(screen.getByLabelText('Origin')).not.toHaveAttribute('aria-invalid')
  })

  it('lets the user pick a candidate for an ambiguous location', async () => {
    evaluateMock.mockRejectedValueOnce(
      new ApiError(422, 'x', {
        error: {
          code: 'ambiguous_location',
          message: '"Temple, TX" matches several places. Please be more specific.',
          query: 'Temple, TX',
          candidates: ['Temple, TX, USA', 'Temple Terrace, FL, USA'],
        },
      }),
    )
    render(<RoutePlanner />)
    const user = await fillValidTrip()
    await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))

    expect(await screen.findByText('Evaluation failed: Which location did you mean?')).toBeInTheDocument()
    expect(screen.getByText('Pick a match to use as the destination:')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Temple Terrace, FL, USA' }))

    expect(screen.getByLabelText('Destination')).toHaveValue('Temple Terrace, FL, USA')
    expect(screen.getByLabelText('Origin')).toHaveValue('Waco, TX')
  })

  it.each([
    [new ApiError(503, 'x', { error: { code: 'routing_not_configured', message: 'Routing is not configured on the server (missing ORS_API_KEY).' } }), 'Routing is not configured on the server'],
    [new ApiError(422, 'x', { error: { code: 'route_not_found', message: 'No drivable truck route was found between these locations.' } }), 'No truck route found'],
    [new ApiError(502, 'x', { error: { code: 'routing_quota_exceeded', message: "The routing provider's daily request quota for this server has been used up." } }), 'Routing service daily limit reached'],
    [new DOMException('slow', 'TimeoutError'), 'The request timed out'],
    [new TypeError('Failed to fetch'), 'Cannot reach the server'],
    [new ApiError(500, 'x', null), 'Server error'],
  ])('distinguishes request failures (%#)', async (error, title) => {
    evaluateMock.mockRejectedValueOnce(error)
    render(<RoutePlanner />)
    const user = await fillValidTrip()

    await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(`Evaluation failed: ${title}`)
    expect(screen.queryByText('No safe route available')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Destination')).toHaveValue('Temple, TX')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Evaluate routes' })).toBeEnabled())
  })
})
