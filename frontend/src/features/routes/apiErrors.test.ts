import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api/client'
import { toPlannerFailure } from './apiErrors'

describe('toPlannerFailure', () => {
  it('maps DRF field errors to validation failures', () => {
    const failure = toPlannerFailure(
      new ApiError(400, 'bad', { departure_time: ['Include a timezone offset.'], load_weight_lbs: ['Must be positive.'] }),
    )
    expect(failure).toEqual({
      kind: 'validation',
      message: 'Please correct the highlighted fields.',
      fieldErrors: { departure_time: 'Include a timezone offset.', load_weight_lbs: 'Must be positive.' },
    })
  })

  it('keeps ambiguous-location candidates and the query', () => {
    const failure = toPlannerFailure(
      new ApiError(422, 'x', {
        error: {
          code: 'ambiguous_location',
          message: '"Springfield" matches several places.',
          query: 'Springfield',
          candidates: ['Springfield, IL, USA', 'Springfield, MO, USA'],
        },
      }),
    )
    expect(failure).toEqual({
      kind: 'routing',
      code: 'ambiguous_location',
      message: '"Springfield" matches several places.',
      query: 'Springfield',
      candidates: ['Springfield, IL, USA', 'Springfield, MO, USA'],
    })
  })

  it('maps provider errors with their backend message', () => {
    const failure = toPlannerFailure(
      new ApiError(503, 'x', { error: { code: 'routing_not_configured', message: 'Routing is not configured.' } }),
    )
    expect(failure).toMatchObject({ kind: 'routing', code: 'routing_not_configured', candidates: [] })
  })

  it('treats routing timeouts and gateway timeouts as timeouts', () => {
    expect(toPlannerFailure(new ApiError(504, 'x', { error: { code: 'routing_timeout', message: 'slow' } })).kind).toBe(
      'timeout',
    )
    expect(toPlannerFailure(new ApiError(504, 'x', null)).kind).toBe('timeout')
  })

  it('treats client-side timeouts as timeouts', () => {
    expect(toPlannerFailure(new DOMException('timed out', 'TimeoutError')).kind).toBe('timeout')
  })

  it('treats fetch failures as network errors', () => {
    expect(toPlannerFailure(new TypeError('Failed to fetch')).kind).toBe('network')
  })

  it('falls back to a server failure for unexpected bodies', () => {
    expect(toPlannerFailure(new ApiError(500, 'x', '<html>'))).toMatchObject({ kind: 'server', status: 500 })
  })

  it('keeps the field a routing error refers to, and drops unknown values', () => {
    const failure = (field: unknown) =>
      toPlannerFailure(new ApiError(422, 'x', { error: { code: 'location_not_routable', message: 'm', field } }))

    expect(failure('destination')).toMatchObject({ kind: 'routing', field: 'destination' })
    expect(failure('somewhere')).toMatchObject({ kind: 'routing', field: undefined })
  })
})

