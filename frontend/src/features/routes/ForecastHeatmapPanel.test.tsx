import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { forecastWindow, observation, safeEvaluation } from '../../test/fixtures'
import ForecastHeatmapPanel, { type ForecastState } from './ForecastHeatmapPanel'
import { observationsAt, uniqueCheckpointLocations } from './heatmap'

const evaluation = safeEvaluation()
const { locations, indexByKey } = uniqueCheckpointLocations(evaluation.routes)
const window = forecastWindow(locations, (i, h) =>
  h === 6 && i === 2 ? observation(null) : h === 6 && i === 1 ? observation('severe', { wind: 47 }) : observation('low'),
)

function renderPanel(forecast: ForecastState, overrides: Partial<Parameters<typeof ForecastHeatmapPanel>[0]> = {}) {
  const points = forecast.status === 'done' ? observationsAt(forecast.window, indexByKey, evaluation.routes[0], 6) : null
  return render(
    <ForecastHeatmapPanel
      enabled
      onToggle={() => {}}
      forecast={forecast}
      onRetry={() => {}}
      departureIso={evaluation.departure_time}
      offsetHours={6}
      onOffsetChange={() => {}}
      routeLabel="Route 1"
      points={points}
      {...overrides}
    />,
  )
}

describe('ForecastHeatmapPanel', () => {
  it('toggles the heatmap', async () => {
    const onToggle = vi.fn()
    renderPanel({ status: 'idle' }, { enabled: false, onToggle })

    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('checkbox', { name: 'Show weather heatmap' }))

    expect(onToggle).toHaveBeenCalledWith(true)
  })

  it('shows a loading state without any data', () => {
    renderPanel({ status: 'loading' })

    expect(screen.getByText('Loading the 48-hour forecast along the routes…')).toBeInTheDocument()
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
    expect(screen.queryByText('Risk legend')).not.toBeInTheDocument()
  })

  it('shows an error with retry and no heatmap', async () => {
    const onRetry = vi.fn()
    renderPanel({ status: 'failed', message: 'The weather service is unavailable.' }, { onRetry })

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Heatmap unavailable')
    expect(alert).toHaveTextContent('No heatmap is shown.')
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalled()
  })

  it('lists every risk level and missing data in the legend', () => {
    renderPanel({ status: 'done', window })

    const legend = screen.getByRole('list', { name: 'Risk legend' })
    expect(within(legend).getAllByRole('listitem').map((li) => li.textContent?.slice(1))).toEqual([
      'Low',
      'Moderate',
      'High',
      'Severe',
      'No Travel',
      'Weather unavailable',
    ])
  })

  it('explains that the layer is checkpoint-based, not radar', () => {
    renderPanel({ status: 'done', window })

    const notice = screen.getByRole('note', { name: '' })
    expect(notice).toHaveTextContent('selected hour')
    expect(notice).toHaveTextContent('nearest checkpoint')
    expect(notice).toHaveTextContent('not radar')
  })

  it('offers a text table with forecast hours and never shows missing data as Low', () => {
    renderPanel({ status: 'done', window })

    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(4)
    expect(within(rows[1]).getByText('47.0 mph')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Severe')).toBeInTheDocument()
    // The forecast hour is stated once, for the selected hour, not repeated per row.
    expect(within(table).getByText(/Conditions at \+6 h \(Mon, Oct 19, 2:00\sPM CDT\), not at each checkpoint/)).toBeInTheDocument()
    expect(within(rows[1]).queryByText(/Forecast hour/)).not.toBeInTheDocument()
    expect(within(rows[2]).getByText('Weather unavailable')).toBeInTheDocument()
    expect(within(rows[2]).getByText('The forecast for this hour is incomplete.')).toBeInTheDocument()
    expect(within(rows[2]).queryByText('Low')).not.toBeInTheDocument()
  })

  it('shows the coverage note when part of the window is beyond the forecast', () => {
    const limited = forecastWindow(locations, () => observation('low'), '20 of 49 hours are beyond the available forecast.')
    renderPanel({ status: 'done', window: limited })

    expect(screen.getByText('20 of 49 hours are beyond the available forecast.')).toBeInTheDocument()
  })

  it('explains what the heatmap does while it is off', () => {
    renderPanel({ status: 'idle' }, { enabled: false })

    expect(screen.getByText('Colour Route 1 by forecast risk for any hour in the next 48 h.')).toBeInTheDocument()
  })

  it('summarises the worst risk at the selected hour and where it is', () => {
    renderPanel({ status: 'done', window })

    expect(screen.getByText('Worst on Route 1 at this hour')).toBeInTheDocument()
    expect(screen.getByText('at checkpoint #1')).toBeInTheDocument()
  })

  it('says "all checkpoints" when the whole route shares the worst risk', () => {
    const calm = forecastWindow(locations, () => observation('low'))
    renderPanel({ status: 'done', window: calm })

    expect(screen.getByText(`at all ${evaluation.routes[0].checkpoints.length} checkpoints`)).toBeInTheDocument()
  })

  it("names a row's own forecast hour only when it differs from the selected hour", () => {
    const shifted = forecastWindow(locations, () => observation('low'))
    const first = shifted.locations[0].observations[6]
    shifted.locations[0].observations[6] = {
      ...first,
      weather: { ...first.weather, forecast_time: '2026-10-19T18:00:00+00:00' },
    }
    renderPanel({ status: 'done', window: shifted })

    const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText(/Forecast hour Mon, Oct 19, 1:00\sPM CDT/)).toBeInTheDocument()
    expect(within(rows[1]).queryByText(/Forecast hour/)).not.toBeInTheDocument()
  })
})

