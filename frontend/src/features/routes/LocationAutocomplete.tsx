import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { getLocationSuggestions } from '../../api/client'
import type { LocationSuggestion } from '../../types/routes'

export const MIN_QUERY_LENGTH = 3
export const SUGGESTION_DEBOUNCE_MS = 300

interface LocationAutocompleteProps {
  id: string
  value: string
  placeholder?: string
  invalid?: boolean
  describedBy?: string
  onChange: (value: string) => void
}

type Status = 'idle' | 'loading' | 'ready' | 'unavailable'

/**
 * Text input with place suggestions (ARIA 1.2 combobox + listbox).
 * Suggestions only help fill the field; the backend still geocodes the submitted text.
 */
function LocationAutocomplete({ id, value, placeholder, invalid, describedBy, onChange }: LocationAutocompleteProps) {
  const listboxId = useId()
  const [suggestions, setSuggestions] = useState<LocationSuggestion[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  // Query waiting for a network lookup. Only text the user typed is looked up, never
  // values set by picking a suggestion or by other parts of the form.
  const [pendingQuery, setPendingQuery] = useState<string | null>(null)
  const cache = useRef(new Map<string, LocationSuggestion[]>())

  useEffect(() => {
    if (pendingQuery === null) return
    const query = pendingQuery
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setStatus('loading')
      try {
        const response = await getLocationSuggestions(query, controller.signal)
        cache.current.set(query.toLowerCase(), response.suggestions)
        setSuggestions(response.suggestions)
        setStatus('ready')
        setActiveIndex(-1)
      } catch {
        // Aborted (newer keystroke) or unavailable: never show stale or partial results.
        if (controller.signal.aborted) return
        setSuggestions([])
        setStatus('unavailable')
      }
    }, SUGGESTION_DEBOUNCE_MS)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [pendingQuery])

  function handleInput(text: string) {
    onChange(text)
    setOpen(true)
    setActiveIndex(-1)
    const query = text.trim()
    const cached = cache.current.get(query.toLowerCase())
    if (query.length < MIN_QUERY_LENGTH) {
      setPendingQuery(null)
      setSuggestions([])
      setStatus('idle')
    } else if (cached) {
      setPendingQuery(null)
      setSuggestions(cached)
      setStatus('ready')
    } else {
      setPendingQuery(query)
    }
  }

  const expanded = open && suggestions.length > 0

  function select(suggestion: LocationSuggestion) {
    onChange(suggestion.label)
    setPendingQuery(null)
    setStatus('idle')
    setSuggestions([])
    setOpen(false)
    setActiveIndex(-1)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' && suggestions.length > 0) {
      event.preventDefault()
      setOpen(true)
      setActiveIndex((index) => (index + 1) % suggestions.length)
    } else if (event.key === 'ArrowUp' && suggestions.length > 0) {
      event.preventDefault()
      setOpen(true)
      setActiveIndex((index) => (index <= 0 ? suggestions.length - 1 : index - 1))
    } else if (event.key === 'Enter' && expanded && activeIndex >= 0) {
      // Pick the highlighted suggestion instead of submitting the form.
      event.preventDefault()
      select(suggestions[activeIndex])
    } else if (event.key === 'Escape' && expanded) {
      event.preventDefault()
      setOpen(false)
      setActiveIndex(-1)
    }
  }

  const statusText =
    status === 'loading'
      ? 'Searching places…'
      : status === 'unavailable'
        ? 'Place suggestions are unavailable.'
        : expanded
          ? `${suggestions.length} suggestion${suggestions.length === 1 ? '' : 's'}. Use up and down arrows to choose.`
          : status === 'ready' && open
            ? 'No matching places.'
            : ''

  return (
    <div className="autocomplete">
      <input
        id={id}
        name={id}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={expanded}
        aria-controls={listboxId}
        aria-activedescendant={expanded && activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedBy}
        placeholder={placeholder}
        value={value}
        onChange={(event) => handleInput(event.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={handleKeyDown}
      />
      <ul id={listboxId} role="listbox" aria-label="Place suggestions" className="autocomplete__list" hidden={!expanded}>
        {suggestions.map((suggestion, index) => (
          <li
            key={suggestion.label}
            id={`${listboxId}-${index}`}
            role="option"
            aria-selected={index === activeIndex}
            className={`autocomplete__option${index === activeIndex ? ' autocomplete__option--active' : ''}`}
            // Keep focus in the input so blur doesn't close the list before the click lands.
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => select(suggestion)}
          >
            {suggestion.label}
          </li>
        ))}
      </ul>
      <span className="visually-hidden" role="status" aria-live="polite">
        {statusText}
      </span>
      {status === 'loading' && open && (
        <span className="autocomplete__hint" aria-hidden="true">
          Searching…
        </span>
      )}
    </div>
  )
}

export default LocationAutocomplete
