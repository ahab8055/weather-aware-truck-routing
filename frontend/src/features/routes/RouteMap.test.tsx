import { render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { partialEvaluation, safeEvaluation } from '../../test/fixtures'
import type { HeatmapSegment } from './heatmap'
import RouteMap from './RouteMap'

// jsdom has no layout or SVG geometry; give Leaflet just enough to render vector layers.
beforeAll(() => {
  Object.defineProperty(SVGSVGElement.prototype, 'createSVGRect', { value: () => ({}), configurable: true })
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { get: () => 800, configurable: true })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { get: () => 600, configurable: true })
})

function renderMap(response = safeEvaluation(), selectedRouteId = 'route-2', heatmap: HeatmapSegment[] | null = null) {
  return render(
    <RouteMap
      routes={response.routes}
      origin={response.origin}
      destination={response.destination}
      selectedRouteId={selectedRouteId}
      selectedCheckpointIndex={0}
      onSelectRoute={vi.fn()}
      onSelectCheckpoint={vi.fn()}
      heatmap={heatmap}
    />,
  )
}

describe('RouteMap (smoke test in jsdom)', () => {
  it('draws one line per route, checkpoints for the selected route and endpoint markers', () => {
    const { container } = renderMap()

    const vectorPaths = container.querySelectorAll('path.leaflet-interactive')
    // 2 route polylines + 4 checkpoint circles on the selected route.
    expect(vectorPaths).toHaveLength(6)
    expect(screen.getByTitle('Origin: Waco, TX, USA')).toBeInTheDocument()
    expect(screen.getByTitle('Destination: Temple, TX, USA')).toBeInTheDocument()
    expect(container.querySelector('.leaflet-control-attribution')).toHaveTextContent('OpenStreetMap')
    expect(container.querySelector('.leaflet-control-zoom')).toBeInTheDocument()
  })

  it('renders unavailable checkpoints with a dashed outline and grey fill', () => {
    const { container } = renderMap(partialEvaluation(), 'route-2')

    const circles = Array.from(container.querySelectorAll('path.leaflet-interactive')).slice(-4)
    expect(circles.filter((c) => c.getAttribute('stroke-dasharray') === '3 3')).toHaveLength(2)
    expect(circles.filter((c) => c.getAttribute('fill') === '#868e96')).toHaveLength(2)
  })
})

describe('RouteMap heatmap layer', () => {
  const segments: HeatmapSegment[] = [
    { checkpointIndex: 0, state: 'low', positions: [[30, -97], [30.2, -97]] },
    { checkpointIndex: 1, state: 'unavailable', positions: [[30.2, -97], [30.6, -97]] },
    { checkpointIndex: 2, state: 'no_travel', positions: [[30.6, -97], [31, -97]] },
  ]

  it('draws non-interactive stretches in a pane below the route lines', () => {
    const { container } = renderMap(safeEvaluation(), 'route-2', segments)

    const pane = container.querySelector('.leaflet-weather-heatmap-pane') as HTMLElement
    expect(pane).not.toBeNull()
    expect(pane.style.zIndex).toBe('350')
    const stretches = pane.querySelectorAll('path.heatmap-segment')
    expect(stretches).toHaveLength(3)
    expect(pane.querySelectorAll('path.leaflet-interactive')).toHaveLength(0)
    // Route lines and checkpoints remain interactive.
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(6)
  })

  it('renders missing data as dashed grey, distinct from Low', () => {
    const { container } = renderMap(safeEvaluation(), 'route-2', segments)

    const low = container.querySelector('path.heatmap-segment--low')
    const missing = container.querySelector('path.heatmap-segment--unavailable')
    expect(low?.getAttribute('stroke')).toBe('#2f9e44')
    expect(low?.getAttribute('stroke-dasharray')).toBeNull()
    expect(missing?.getAttribute('stroke')).toBe('#868e96')
    expect(missing?.getAttribute('stroke-dasharray')).toBe('6 10')
  })

  it('draws nothing when the heatmap is hidden', () => {
    const { container } = renderMap(safeEvaluation(), 'route-2', null)

    expect(container.querySelectorAll('path.heatmap-segment')).toHaveLength(0)
  })
})
