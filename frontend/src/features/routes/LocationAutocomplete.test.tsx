import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getLocationSuggestions } from '../../api/client'
import type { LocationSuggestionsResponse } from '../../types/routes'
import LocationAutocomplete from './LocationAutocomplete'

vi.mock('../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/client')>()
  return { ...actual, getLocationSuggestions: vi.fn() }
})

const suggestMock = vi.mocked(getLocationSuggestions)

const HOUSTON: LocationSuggestionsResponse = {
  query: 'Hous',
  suggestions: [
    { label: 'Houston, TX, USA', latitude: 29.78, longitude: -95.36 },
    { label: 'Houston, MN, USA', latitude: 43.76, longitude: -91.57 },
    { label: 'Houston County, GA, USA', latitude: 32.42, longitude: -83.67 },
  ],
}

function Harness({ onSubmit = () => {} }: { onSubmit?: () => void }) {
  const [value, setValue] = useState('')
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <label htmlFor="destination">Destination</label>
      <LocationAutocomplete id="destination" value={value} onChange={setValue} />
      <button type="submit">Submit</button>
    </form>
  )
}

function input() {
  return screen.getByRole('combobox', { name: 'Destination' })
}

beforeEach(() => {
  suggestMock.mockReset()
})

describe('LocationAutocomplete', () => {
  it('waits for 3 characters before searching', async () => {
    suggestMock.mockResolvedValue(HOUSTON)
    render(<Harness />)

    await userEvent.type(input(), 'Ho')
    await new Promise((r) => setTimeout(r, 400))

    expect(suggestMock).not.toHaveBeenCalled()
    expect(input()).toHaveAttribute('aria-expanded', 'false')
  })

  it('debounces typing into a single request and lists suggestions', async () => {
    suggestMock.mockResolvedValue(HOUSTON)
    render(<Harness />)

    await userEvent.type(input(), 'Hous')

    const options = await screen.findAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual([
      'Houston, TX, USA',
      'Houston, MN, USA',
      'Houston County, GA, USA',
    ])
    expect(suggestMock).toHaveBeenCalledTimes(1)
    expect(suggestMock.mock.calls[0][0]).toBe('Hous')
    expect(input()).toHaveAttribute('aria-expanded', 'true')
    expect(input()).toHaveAttribute('aria-controls', screen.getByRole('listbox').id)
    expect(screen.getByRole('status')).toHaveTextContent('3 suggestions')
  })

  it('selects a suggestion with the keyboard without submitting the form', async () => {
    suggestMock.mockResolvedValue(HOUSTON)
    const onSubmit = vi.fn()
    render(<Harness onSubmit={onSubmit} />)
    const user = userEvent.setup()
    await user.type(input(), 'Hous')
    await screen.findAllByRole('option')

    await user.keyboard('{ArrowDown}{ArrowDown}')
    const active = screen.getByRole('option', { selected: true })
    expect(active).toHaveTextContent('Houston, MN, USA')
    expect(input()).toHaveAttribute('aria-activedescendant', active.id)

    await user.keyboard('{Enter}')

    expect(input()).toHaveValue('Houston, MN, USA')
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.queryByRole('option')).not.toBeInTheDocument()
    expect(input()).toHaveAttribute('aria-expanded', 'false')
  })

  it('wraps around with the arrow keys', async () => {
    suggestMock.mockResolvedValue(HOUSTON)
    render(<Harness />)
    const user = userEvent.setup()
    await user.type(input(), 'Hous')
    await screen.findAllByRole('option')

    await user.keyboard('{ArrowUp}')

    expect(screen.getByRole('option', { selected: true })).toHaveTextContent('Houston County, GA, USA')
  })

  it('selects a suggestion with the mouse', async () => {
    suggestMock.mockResolvedValue(HOUSTON)
    render(<Harness />)
    const user = userEvent.setup()
    await user.type(input(), 'Hous')

    await user.click(await screen.findByRole('option', { name: 'Houston, TX, USA' }))

    expect(input()).toHaveValue('Houston, TX, USA')
    // Picking a suggestion does not trigger another lookup.
    await new Promise((r) => setTimeout(r, 400))
    expect(suggestMock).toHaveBeenCalledTimes(1)
  })

  it('submits normally on Enter when no suggestion is highlighted', async () => {
    suggestMock.mockResolvedValue(HOUSTON)
    const onSubmit = vi.fn()
    render(<Harness onSubmit={onSubmit} />)
    const user = userEvent.setup()
    await user.type(input(), 'Hous')
    await screen.findAllByRole('option')

    await user.keyboard('{Enter}')

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(input()).toHaveValue('Hous')
  })

  it('closes on Escape and on blur', async () => {
    suggestMock.mockResolvedValue(HOUSTON)
    render(<Harness />)
    const user = userEvent.setup()
    await user.type(input(), 'Hous')
    await screen.findAllByRole('option')

    await user.keyboard('{Escape}')
    expect(input()).toHaveAttribute('aria-expanded', 'false')

    await user.keyboard('{ArrowDown}')
    expect(input()).toHaveAttribute('aria-expanded', 'true')

    await user.tab()
    expect(input()).toHaveAttribute('aria-expanded', 'false')
  })

  it('reuses cached results for a repeated query', async () => {
    suggestMock.mockResolvedValue(HOUSTON)
    render(<Harness />)
    const user = userEvent.setup()
    await user.type(input(), 'Hous')
    await screen.findAllByRole('option')

    await user.type(input(), '{Backspace}')
    await user.type(input(), 's')

    expect(await screen.findAllByRole('option')).toHaveLength(3)
    expect(suggestMock).toHaveBeenCalledTimes(1)
  })

  it('ignores responses for outdated input', async () => {
    let resolveOld: (value: LocationSuggestionsResponse) => void = () => {}
    suggestMock
      .mockImplementationOnce(
        (_query, signal) =>
          new Promise((resolve, reject) => {
            resolveOld = resolve
            signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
          }),
      )
      .mockResolvedValueOnce({ query: 'Housto', suggestions: [HOUSTON.suggestions[0]] })
    render(<Harness />)

    fireEvent.change(input(), { target: { value: 'Hous' } })
    await waitFor(() => expect(suggestMock).toHaveBeenCalledTimes(1))
    fireEvent.change(input(), { target: { value: 'Housto' } })
    await waitFor(() => expect(suggestMock).toHaveBeenCalledTimes(2))
    await act(async () => resolveOld(HOUSTON))

    const options = await screen.findAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(['Houston, TX, USA'])
  })

  it('hides suggestions when the service is unavailable', async () => {
    suggestMock.mockRejectedValue(
      new ApiError(503, 'x', { error: { code: 'routing_not_configured', message: 'not configured' } }),
    )
    render(<Harness />)

    await userEvent.type(input(), 'Hous')

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Place suggestions are unavailable.'))
    expect(screen.queryByRole('option')).not.toBeInTheDocument()
    expect(input()).toHaveValue('Hous')
  })

  it('says when nothing matches', async () => {
    suggestMock.mockResolvedValue({ query: 'Xyzz', suggestions: [] })
    render(<Harness />)

    await userEvent.type(input(), 'Xyzz')

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('No matching places.'))
    expect(input()).toHaveAttribute('aria-expanded', 'false')
  })
})
