const milesFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1, minimumFractionDigits: 1 })

export function formatMiles(miles: number): string {
  return `${milesFormat.format(miles)} mi`
}

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) return `${minutes} min`
  return `${hours} h ${String(minutes).padStart(2, '0')} min`
}

export function formatMph(mph: number): string {
  return `${mph.toFixed(1)} mph`
}

export function formatInchesPerHour(inches: number): string {
  return `${inches.toFixed(2)} in/hr`
}

export function formatRiskScore(score: number): string {
  return score.toFixed(2)
}

const localDateTime = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})

/** An ISO timestamp shown in the user's local timezone. */
export function formatLocalDateTime(iso: string): string {
  return localDateTime.format(new Date(iso))
}
