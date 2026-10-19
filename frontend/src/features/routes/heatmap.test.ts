import { describe, expect, it } from 'vitest'
import { forecastWindow, observation, route, safeEvaluation } from '../../test/fixtures'
import {
  corridorSegments,
  observationsAt,
  selectedTime,
  uniqueCheckpointLocations,
  etaOffsetHours,
  worstState,
  worstStateByHour,
} from './heatmap'

describe('uniqueCheckpointLocations', () => {
  it('dedupes identical checkpoint coordinates across routes', () => {
    const { routes } = safeEvaluation()
    const { locations, indexByKey } = uniqueCheckpointLocations(routes)

    // Both fixture routes share checkpoint coordinates: 8 checkpoints -> 4 locations.
    expect(routes.flatMap((r) => r.checkpoints)).toHaveLength(8)
    expect(locations).toHaveLength(4)
    expect(locations[0]).toEqual({ latitude: 30, longitude: -97 })
    expect(indexByKey.size).toBe(4)
  })
})

describe('selectedTime', () => {
  it('adds whole hours to the departure instant', () => {
    expect(selectedTime('2026-10-19T08:00:00-05:00', 0).toISOString()).toBe('2026-10-19T13:00:00.000Z')
    expect(selectedTime('2026-10-19T08:00:00-05:00', 6).toISOString()).toBe('2026-10-19T19:00:00.000Z')
    expect(selectedTime('2026-10-19T08:00:00-05:00', 48).toISOString()).toBe('2026-10-21T13:00:00.000Z')
  })

  it('adds elapsed time across a DST change', () => {
    // US DST ends 2026-11-01 02:00 local; 24 h later is 07:00 CST (-06:00), not 08:00.
    expect(selectedTime('2026-10-31T08:00:00-05:00', 24).toISOString()).toBe('2026-11-01T13:00:00.000Z')
  })
})

describe('observationsAt', () => {
  it('returns each checkpoint observation for the slot and marks missing data unavailable', () => {
    const evaluation = safeEvaluation()
    const { locations, indexByKey } = uniqueCheckpointLocations(evaluation.routes)
    const window = forecastWindow(locations, (i, h) =>
      h === 6 && i === 1 ? observation('severe', { wind: 47 }) : h === 6 && i === 2 ? observation(null) : observation('low'),
    )

    const atZero = observationsAt(window, indexByKey, evaluation.routes[0], 0)
    const atSix = observationsAt(window, indexByKey, evaluation.routes[0], 6)

    expect(atZero.map((p) => p.state)).toEqual(['low', 'low', 'low', 'low'])
    expect(atSix.map((p) => p.state)).toEqual(['low', 'severe', 'unavailable', 'low'])
    expect(atSix[1].observation?.weather.forecast_time).toBe('2026-10-19T19:00:00+00:00')
    expect(atSix[2].observation?.risk).toBeNull()
  })
})

describe('corridorSegments', () => {
  it('splits the route at midpoints between checkpoints, contiguous from end to end', () => {
    // Straight north along -97 from 30 to 31 (~69.09 mi); checkpoints at 0, 25, 50, 69.09.
    const r = route(0, {
      distance_miles: 69.0934,
      geometry: [
        [30, -97],
        [30.1, -97],
        [31, -97],
      ],
    })
    r.checkpoints = r.checkpoints.map((c, i) => ({ ...c, distance_miles: [0, 25, 50, 69.0934][i] }))

    const segments = corridorSegments(r, ['low', 'severe', 'unavailable', 'high'])

    expect(segments.map((s) => s.state)).toEqual(['low', 'severe', 'unavailable', 'high'])
    expect(segments[0].positions[0]).toEqual([30, -97])
    expect(segments.at(-1)?.positions.at(-1)).toEqual([31, -97])
    for (let i = 1; i < segments.length; i += 1) {
      expect(segments[i].positions[0]).toEqual(segments[i - 1].positions.at(-1))
    }
    // Boundaries at miles 12.5, 37.5 and 59.55 along the line (~0.1809° per 12.5 mi).
    expect(segments[0].positions.at(-1)?.[0]).toBeCloseTo(30 + 12.5 / 69.0934, 4)
    expect(segments[1].positions.at(-1)?.[0]).toBeCloseTo(30 + 37.5 / 69.0934, 4)
    // The 30.1 vertex lies inside the first stretch (0–12.5 mi), so it is kept there.
    expect(segments[0].positions).toContainEqual([30.1, -97])
  })

  it('returns no segments for degenerate routes', () => {
    expect(corridorSegments(route(0, { geometry: [[30, -97]] }), ['low'])).toEqual([])
  })
})

describe('worstState', () => {
  it('returns the highest assessed risk and ignores missing data', () => {
    expect(worstState(['low', 'unavailable', 'severe', 'moderate'])).toBe('severe')
    expect(worstState(['high', 'no_travel'])).toBe('no_travel')
  })

  it('is unavailable only when nothing was assessed', () => {
    expect(worstState(['unavailable', 'unavailable'])).toBe('unavailable')
    expect(worstState([])).toBe('unavailable')
  })
})

describe('worstStateByHour', () => {
  it('gives the worst state along the route for every slot', () => {
    const evaluation = safeEvaluation()
    const { locations, indexByKey } = uniqueCheckpointLocations(evaluation.routes)
    const window = forecastWindow(locations, (i, h) =>
      h === 3 && i === 1 ? observation('high') : h === 5 ? observation(null) : observation('low'),
    )

    const timeline = worstStateByHour(window, indexByKey, evaluation.routes[0])

    expect(timeline).toHaveLength(window.slots.length)
    expect(timeline[0]).toBe('low')
    expect(timeline[3]).toBe('high')
    expect(timeline[5]).toBe('unavailable')
  })
})

describe('etaOffsetHours', () => {
  const departure = '2026-10-19T08:00:00-05:00'

  it('rounds the ETA to the nearest forecast hour after departure', () => {
    expect(etaOffsetHours(departure, '2026-10-19T14:20:00-05:00')).toBe(6)
    expect(etaOffsetHours(departure, '2026-10-19T14:40:00-05:00')).toBe(7)
  })

  it('is null outside the 0–48 h window', () => {
    expect(etaOffsetHours(departure, '2026-10-21T09:00:00-05:00')).toBeNull()
    expect(etaOffsetHours(departure, 'not a date')).toBeNull()
  })
})

