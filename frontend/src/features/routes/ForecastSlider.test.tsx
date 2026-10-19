import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ForecastSlider from './ForecastSlider'
import type { CheckpointRiskState } from './riskDisplay'

const DEPARTURE = '2026-10-19T08:00:00-05:00'

describe('ForecastSlider', () => {
  it('spans 0–48 hours in 1-hour steps with labelled ticks', () => {
    render(<ForecastSlider departureIso={DEPARTURE} offsetHours={0} forecastTime={null} onChange={() => {}} />)

    const slider = screen.getByRole('slider', { name: 'Forecast time (hours after departure)' })
    expect(slider).toHaveAttribute('min', '0')
    expect(slider).toHaveAttribute('max', '48')
    expect(slider).toHaveAttribute('step', '1')
    for (const label of ['Departure', '+12 h', '+24 h', '+36 h', '+48 h']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
  })

  it('shows the selected offset and local datetime, including for screen readers', () => {
    render(
      <ForecastSlider
        departureIso={DEPARTURE}
        offsetHours={6}
        forecastTime="2026-10-19T19:00:00+00:00"
        onChange={() => {}}
      />,
    )

    const slider = screen.getByRole('slider')
    expect(slider).toHaveValue('6')
    expect(slider.getAttribute('aria-valuetext')).toMatch(/^\+6 h, Mon, Oct 19, 2:00\sPM CDT$/)
    expect(screen.getByText('+6 h')).toBeInTheDocument()
    expect(screen.getByText(/Forecast hour used: Mon, Oct 19, 2:00\sPM CDT/)).toBeInTheDocument()
  })

  it('says when no forecast exists for the selected hour', () => {
    render(<ForecastSlider departureIso={DEPARTURE} offsetHours={48} forecastTime={null} onChange={() => {}} />)

    expect(screen.getByText(/no forecast available for this hour/)).toBeInTheDocument()
  })

  it('reports changes as whole hours', () => {
    const onChange = vi.fn()
    render(<ForecastSlider departureIso={DEPARTURE} offsetHours={0} forecastTime={null} onChange={onChange} />)

    fireEvent.change(screen.getByRole('slider'), { target: { value: '12' } })

    expect(onChange).toHaveBeenCalledWith(12)
  })

  it('steps one hour with the previous and next buttons, clamped to the window', () => {
    const onChange = vi.fn()
    const { rerender } = render(
      <ForecastSlider departureIso={DEPARTURE} offsetHours={0} forecastTime={null} onChange={onChange} />,
    )

    expect(screen.getByRole('button', { name: 'Previous hour' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Next hour' }))
    expect(onChange).toHaveBeenLastCalledWith(1)

    rerender(<ForecastSlider departureIso={DEPARTURE} offsetHours={48} forecastTime={null} onChange={onChange} />)
    expect(screen.getByRole('button', { name: 'Next hour' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Previous hour' }))
    expect(onChange).toHaveBeenLastCalledWith(47)
  })

  it('plays through the hours and pauses', () => {
    vi.useFakeTimers()
    try {
      let offset = 46
      const onChange = vi.fn((value: number) => {
        offset = value
      })
      const view = () => (
        <ForecastSlider departureIso={DEPARTURE} offsetHours={offset} forecastTime={null} onChange={onChange} />
      )
      const { rerender } = render(view())

      fireEvent.click(screen.getByRole('button', { name: 'Play forecast' }))
      act(() => vi.advanceTimersByTime(700))
      rerender(view())
      expect(onChange).toHaveBeenLastCalledWith(47)
      act(() => vi.advanceTimersByTime(700))
      rerender(view())
      expect(onChange).toHaveBeenLastCalledWith(48)

      // Stops by itself at the end of the window.
      act(() => vi.advanceTimersByTime(700))
      rerender(view())
      expect(screen.getByRole('button', { name: 'Play forecast' })).toHaveAttribute('aria-pressed', 'false')
      expect(onChange).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('draws the per-hour risk timeline when given one', () => {
    const timeline = Array.from({ length: 49 }, (_, h): CheckpointRiskState => (h === 6 ? 'severe' : 'low'))
    render(
      <ForecastSlider departureIso={DEPARTURE} offsetHours={6} forecastTime={null} onChange={() => {}} timeline={timeline} />,
    )

    const slots = screen.getByTestId('forecast-timeline').children
    expect(slots).toHaveLength(49)
    expect(slots[6]).toHaveClass('forecast-timeline__slot--severe', 'forecast-timeline__slot--current')
  })
})

