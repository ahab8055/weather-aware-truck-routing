import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { allUnsafeEvaluation, partialEvaluation, safeEvaluation } from '../../test/fixtures'
import RouteComparison from './RouteComparison'

function cards() {
  return screen.getAllByRole('button', { pressed: undefined }).filter((b) => b.classList.contains('route-card'))
}

describe('RouteComparison', () => {
  it('shows backend summary values for every route', () => {
    render(<RouteComparison response={safeEvaluation()} selectedRouteId="route-2" onSelectRoute={() => {}} />)

    const [first, second] = cards()
    expect(within(first).getByText('Route 1')).toBeInTheDocument()
    expect(within(first).getByText('12.5 mi')).toBeInTheDocument()
    expect(within(first).getByText('0.54')).toBeInTheDocument()
    expect(within(first).getByText('1 h 10 min')).toBeInTheDocument()
    expect(within(first).getByText('Rank 2 of 2')).toBeInTheDocument()
    expect(within(second).getByText('Recommended')).toBeInTheDocument()
    expect(within(second).getByText('1 h 20 min')).toBeInTheDocument()
    expect(second).toHaveAttribute('aria-pressed', 'true')
    expect(within(first).queryByText('Recommended')).not.toBeInTheDocument()
  })

  it('does not mark unsafe routes as recommended', () => {
    render(<RouteComparison response={allUnsafeEvaluation()} selectedRouteId="route-1" onSelectRoute={() => {}} />)

    expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
    expect(screen.getAllByText('Unsafe: No Travel')).toHaveLength(2)
    expect(screen.getAllByText('N/A (No Travel)')).toHaveLength(2)
    expect(screen.getAllByText('Contains 25.0 miles of No Travel conditions.')).toHaveLength(2)
  })

  it('marks the best evaluated route as a provisional pick, not Recommended, when the comparison is inconclusive', () => {
    render(<RouteComparison response={partialEvaluation()} selectedRouteId="route-1" onSelectRoute={() => {}} />)

    const [first] = cards()
    expect(within(first).getByText('Provisional pick')).toBeInTheDocument()
    expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
  })

  it('labels routes without weather as not fully evaluated', () => {
    render(<RouteComparison response={partialEvaluation()} selectedRouteId="route-1" onSelectRoute={() => {}} />)

    const second = cards()[1]
    expect(within(second).getByText('Not fully evaluated')).toBeInTheDocument()
    expect(within(second).getAllByText('Unavailable')).toHaveLength(4)
    expect(within(second).queryByText(/Rank/)).not.toBeInTheDocument()
  })

  it('selects a route when its card is clicked', async () => {
    const onSelect = vi.fn()
    render(<RouteComparison response={safeEvaluation()} selectedRouteId="route-2" onSelectRoute={onSelect} />)

    await userEvent.click(cards()[0])

    expect(onSelect).toHaveBeenCalledWith('route-1')
  })

  it('shows miles by risk level as a labelled bar', () => {
    render(<RouteComparison response={allUnsafeEvaluation()} selectedRouteId="route-1" onSelectRoute={() => {}} />)

    const [bar] = within(cards()[0]).getAllByRole('img')
    expect(bar).toHaveAccessibleName(/^Risk by distance: No Travel 25\.0 mi, Severe 0\.0 mi, High 0\.0 mi, Low–Moderate/)
  })

  it('omits the risk bar for routes without a summary', () => {
    render(<RouteComparison response={partialEvaluation()} selectedRouteId="route-1" onSelectRoute={() => {}} />)

    expect(within(cards()[0]).getByTestId('risk-mileage-bar')).toBeInTheDocument()
    expect(within(cards()[1]).queryByTestId('risk-mileage-bar')).not.toBeInTheDocument()
  })
})
