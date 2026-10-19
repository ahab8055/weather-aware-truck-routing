import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, evaluateRoutes, getForecastWindow } from '../../api/client'
import type { ForecastWindowResponse } from '../../types/weather'
import { forecastWindow, observation, safeEvaluation } from '../../test/fixtures'
import RoutePlanner from './RoutePlanner'
import type { RouteMapProps } from './RouteMap'
import { uniqueCheckpointLocations } from './heatmap'

vi.mock('../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/client')>()
  return {
    ...actual,
    evaluateRoutes: vi.fn(),
    getForecastWindow: vi.fn(),
    getLocationSuggestions: vi.fn().mockResolvedValue({ query: '', suggestions: [] }),
  }
})

// Map stub exposing the props the planner passes, including heatmap segment states.
vi.mock('./RouteMap', () => ({
  default: (props: RouteMapProps) => (
    <div
      data-testid="route-map"
      data-selected-route={props.selectedRouteId}
      data-heatmap={props.heatmap ? props.heatmap.map((s) => s.state).join(',') : 'none'}
    >
      {props.routes.map((r) => (
        <button key={r.id} type="button" onClick={() => props.onSelectRoute(r.id)}>
          map line {r.id}
        </button>
      ))}
    </div>
  ),
}))

const evaluateMock = vi.mocked(evaluateRoutes)
const windowMock = vi.mocked(getForecastWindow)

const evaluation = safeEvaluation()
const { locations } = uniqueCheckpointLocations(evaluation.routes)
// Location 1 turns Severe and location 2 loses data at +6 h; everything else is Low.
const WINDOW = forecastWindow(locations, (i, h) =>
  h === 6 && i === 1 ? observation('severe', { wind: 47 }) : h === 6 && i === 2 ? observation(null) : observation('low'),
)

async function evaluateTrip() {
  render(<RoutePlanner />)
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Origin'), 'Waco, TX')
  await user.type(screen.getByLabelText('Destination'), 'Temple, TX')
  fireEvent.change(screen.getByLabelText('Departure'), { target: { value: '2026-10-19T08:00' } })
  await user.type(screen.getByLabelText('Truck + load weight (lb)'), '42000')
  await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))
  await screen.findByText('Recommended: Route 2')
  return user
}

function map() {
  return screen.getByTestId('route-map')
}

beforeEach(() => {
  evaluateMock.mockReset()
  windowMock.mockReset()
  evaluateMock.mockResolvedValue(evaluation)
})

describe('RoutePlanner heatmap', () => {
  it('is off by default and makes no forecast request', async () => {
    await evaluateTrip()

    expect(map()).toHaveAttribute('data-heatmap', 'none')
    expect(windowMock).not.toHaveBeenCalled()
  })

  it("turns the heatmap on at the selected checkpoint's ETA", async () => {
    windowMock.mockResolvedValue(WINDOW)
    const user = await evaluateTrip()
    const rows = within(screen.getByRole('region', { name: /checkpoints \(\d+\)$/ })).getAllByRole('button')
    await user.click(rows[rows.length - 1])

    const button = screen.getByRole('button', { name: /^Show on heatmap at ETA \(\+\d+ h\)$/ })
    const hours = Number(/\+(\d+) h/.exec(button.textContent ?? '')?.[1])
    await user.click(button)

    expect(screen.getByRole('checkbox', { name: 'Show weather heatmap' })).toBeChecked()
    expect(await screen.findByRole('slider')).toHaveValue(String(hours))
    expect(windowMock).toHaveBeenCalledTimes(1)
  })

  it('fetches the 48-hour window once with deduplicated checkpoint locations', async () => {
    windowMock.mockResolvedValue(WINDOW)
    const user = await evaluateTrip()

    await user.click(screen.getByRole('checkbox', { name: 'Show weather heatmap' }))

    expect(await screen.findByRole('slider')).toBeInTheDocument()
    expect(windowMock).toHaveBeenCalledTimes(1)
    expect(windowMock.mock.calls[0][0]).toEqual({
      locations,
      departure_time: evaluation.departure_time,
      load_weight_lbs: 42000,
    })
    expect(windowMock.mock.calls[0][0].locations).toHaveLength(4)
    expect(map()).toHaveAttribute('data-heatmap', 'low,low,low,low')
  })

  it('updates the heatmap when the time changes, without new requests or losing the route', async () => {
    windowMock.mockResolvedValue(WINDOW)
    const user = await evaluateTrip()
    await user.click(screen.getByRole('button', { name: 'map line route-1' }))
    await user.click(screen.getByRole('checkbox', { name: 'Show weather heatmap' }))
    const slider = await screen.findByRole('slider')

    fireEvent.change(slider, { target: { value: '6' } })

    expect(map()).toHaveAttribute('data-heatmap', 'low,severe,unavailable,low')
    expect(map()).toHaveAttribute('data-selected-route', 'route-1')
    expect(screen.getByText(/Forecast hour used: Mon, Oct 19, 2:00\sPM CDT/)).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('Weather unavailable')).toBeInTheDocument()
    expect(windowMock).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: 'map line route-2' }))
    expect(map()).toHaveAttribute('data-selected-route', 'route-2')
    expect(screen.getByRole('slider')).toHaveValue('6')
    expect(windowMock).toHaveBeenCalledTimes(1)
  })

  it('shows loading without drawing anything, then the layer', async () => {
    let resolve: (value: ForecastWindowResponse) => void = () => {}
    windowMock.mockReturnValueOnce(new Promise((r) => (resolve = r)))
    const user = await evaluateTrip()

    await user.click(screen.getByRole('checkbox', { name: 'Show weather heatmap' }))

    expect(screen.getByText('Loading the 48-hour forecast along the routes…')).toBeInTheDocument()
    expect(map()).toHaveAttribute('data-heatmap', 'none')
    resolve(WINDOW)
    expect(await screen.findByRole('slider')).toBeInTheDocument()
    expect(map()).toHaveAttribute('data-heatmap', 'low,low,low,low')
  })

  it('shows an error and no layer when the forecast request fails, then retries', async () => {
    windowMock.mockRejectedValueOnce(new ApiError(500, 'x', null)).mockResolvedValueOnce(WINDOW)
    const user = await evaluateTrip()

    await user.click(screen.getByRole('checkbox', { name: 'Show weather heatmap' }))

    expect(await screen.findByText('Heatmap unavailable')).toBeInTheDocument()
    expect(map()).toHaveAttribute('data-heatmap', 'none')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('slider')).toBeInTheDocument()
    expect(windowMock).toHaveBeenCalledTimes(2)
  })

  it('ignores a stale forecast response after a newer evaluation', async () => {
    let resolveStale: (value: ForecastWindowResponse) => void = () => {}
    windowMock.mockReturnValueOnce(new Promise((r) => (resolveStale = r)))
    const user = await evaluateTrip()
    await user.click(screen.getByRole('checkbox', { name: 'Show weather heatmap' }))

    const fresh = forecastWindow(locations, () => observation('moderate'))
    windowMock.mockResolvedValueOnce(fresh)
    await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))
    await screen.findByRole('slider')
    expect(map()).toHaveAttribute('data-heatmap', 'moderate,moderate,moderate,moderate')

    resolveStale(WINDOW)
    await Promise.resolve()
    expect(map()).toHaveAttribute('data-heatmap', 'moderate,moderate,moderate,moderate')
    expect(windowMock).toHaveBeenCalledTimes(2)
  })

  it('hides the layer when toggled off and resets the time on a new evaluation', async () => {
    windowMock.mockResolvedValue(WINDOW)
    const user = await evaluateTrip()
    await user.click(screen.getByRole('checkbox', { name: 'Show weather heatmap' }))
    fireEvent.change(await screen.findByRole('slider'), { target: { value: '6' } })

    await user.click(screen.getByRole('checkbox', { name: 'Show weather heatmap' }))
    expect(map()).toHaveAttribute('data-heatmap', 'none')

    await user.click(screen.getByRole('checkbox', { name: 'Show weather heatmap' }))
    expect(screen.getByRole('slider')).toHaveValue('6')
    expect(windowMock).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: 'Evaluate routes' }))
    expect(await screen.findByRole('slider')).toHaveValue('0')
  })
})
