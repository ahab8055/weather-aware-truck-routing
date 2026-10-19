/** Per-route line style: colour plus dash pattern, so routes differ without relying on colour. */
export interface RouteStyle {
  color: string
  dashArray: string | undefined
  cssLineStyle: 'solid' | 'dashed' | 'dotted'
}

const ROUTE_STYLES: readonly RouteStyle[] = [
  { color: '#008080', dashArray: undefined, cssLineStyle: 'solid' },
  { color: '#4263eb', dashArray: '12 8', cssLineStyle: 'dashed' },
  { color: '#ae3ec9', dashArray: '2 8', cssLineStyle: 'dotted' },
]

export function routeStyle(providerOrder: number): RouteStyle {
  return ROUTE_STYLES[providerOrder % ROUTE_STYLES.length]
}
