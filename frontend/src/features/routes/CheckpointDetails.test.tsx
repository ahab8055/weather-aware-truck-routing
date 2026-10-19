import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { checkpoint, risk, weatherAvailable, weatherUnavailable } from '../../test/fixtures'
import CheckpointDetails from './CheckpointDetails'

describe('CheckpointDetails', () => {
  it('shows weather values, per-hazard risk and the load rule', () => {
    const cp = checkpoint(
      2,
      50,
      weatherAvailable(46.2, 0.3, 0.75, '2026-10-19T14:00:00+00:00'),
      risk('no_travel', { wind: 'severe', rain: 'high', snow: 'moderate', base: 'severe' }, 'heavy_load_wind_no_travel'),
    )

    render(<CheckpointDetails checkpoint={cp} routeLabel="Route 1" />)

    expect(screen.getByText('Route 1 · Checkpoint #2')).toBeInTheDocument()
    expect(screen.getByText('50.0 mi')).toBeInTheDocument()
    expect(screen.getByText('Overall: No Travel')).toBeInTheDocument()
    expect(screen.getByText('46.2 mph')).toBeInTheDocument()
    expect(screen.getByText('0.30 in/hr')).toBeInTheDocument()
    expect(screen.getByText('0.75 in/hr')).toBeInTheDocument()
    expect(screen.getByText('Severe')).toBeInTheDocument()
    expect(screen.getByText('High')).toBeInTheDocument()
    expect(screen.getByText('Moderate')).toBeInTheDocument()
    expect(screen.getByText(/Raised to No Travel: wind is 45 mph or more and the load is over 30,000 lb/)).toBeInTheDocument()
    // Forecast hour 14:00 UTC shown in the user's timezone (America/Chicago in tests).
    expect(screen.getByText(/9:00\sAM CDT/)).toBeInTheDocument()
  })

  it('explains unavailable weather and never shows Low', () => {
    render(<CheckpointDetails checkpoint={checkpoint(3, 70, weatherUnavailable(), null)} routeLabel="Route 2" />)

    expect(screen.getByText('Overall: Weather unavailable')).toBeInTheDocument()
    expect(screen.getByText('Weather unavailable: risk not assessed')).toBeInTheDocument()
    expect(screen.getByText(/outside the available forecast/)).toBeInTheDocument()
    expect(screen.getByText('This checkpoint is not treated as safe.')).toBeInTheDocument()
    expect(screen.queryByText(/\bLow\b/)).not.toBeInTheDocument()
    expect(screen.getByText('None')).toBeInTheDocument()
  })
})
