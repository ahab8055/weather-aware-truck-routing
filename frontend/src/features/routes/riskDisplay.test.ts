import { describe, expect, it } from 'vitest'
import { checkpoint, risk, route, summary, weatherAvailable, weatherUnavailable } from '../../test/fixtures'
import { RISK_LABELS, checkpointRiskState, riskSegments, routeSafety } from './riskDisplay'

describe('checkpointRiskState', () => {
  it('uses the backend overall risk', () => {
    expect(checkpointRiskState(checkpoint(1, 25, weatherAvailable(47, 0, 0), risk('severe')))).toBe('severe')
  })

  it('reports missing weather as unavailable, never low', () => {
    const state = checkpointRiskState(checkpoint(1, 25, weatherUnavailable(), null))
    expect(state).toBe('unavailable')
    expect(RISK_LABELS[state]).toBe('Weather unavailable')
  })
})

describe('routeSafety', () => {
  it('reads safety from the backend summary', () => {
    expect(routeSafety(route(0))).toBe('safe')
    expect(routeSafety(route(0, { summary: summary({ is_safe: false, has_no_travel: true }) }))).toBe('unsafe')
  })

  it('marks routes without a summary as not evaluated', () => {
    expect(routeSafety(route(0, { evaluation_status: 'weather_unavailable', summary: null }))).toBe('not_evaluated')
  })
})

describe('riskSegments', () => {
  it('splits route miles into flagged bands and a Low–Moderate remainder', () => {
    const segments = riskSegments(summary({ no_travel_miles: 5, severe_miles: 10, high_miles: 15, total_distance_miles: 70 }))
    expect(segments.map((s) => [s.label, s.miles])).toEqual([
      ['No Travel', 5],
      ['Severe', 10],
      ['High', 15],
      ['Low–Moderate', 40],
    ])
  })

  it('never reports a negative remainder', () => {
    const segments = riskSegments(summary({ severe_miles: 80, total_distance_miles: 70 }))
    expect(segments.at(-1)?.miles).toBe(0)
  })
})
