import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import {
  CircleMarker,
  MapContainer,
  Marker,
  Pane,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'
import type { EvaluatedRoute, ResolvedLocation } from '../../types/routes'
import CheckpointDetails from './CheckpointDetails'
import type { HeatmapSegment } from './heatmap'
import { RISK_COLORS, RISK_LABELS, checkpointRiskState } from './riskDisplay'
import { routeStyle } from './routeStyles'

export interface RouteMapProps {
  routes: EvaluatedRoute[]
  origin: ResolvedLocation
  destination: ResolvedLocation
  selectedRouteId: string | null
  selectedCheckpointIndex: number
  onSelectRoute: (routeId: string) => void
  onSelectCheckpoint: (index: number) => void
  /** Checkpoint-based weather stretches for the selected hour, or null when hidden. */
  heatmap?: HeatmapSegment[] | null
}

function endpointIcon(letter: string, modifier: string) {
  return L.divIcon({
    className: `map-pin map-pin--${modifier}`,
    html: `<span>${letter}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
}

const ORIGIN_ICON = endpointIcon('A', 'origin')
const DESTINATION_ICON = endpointIcon('B', 'destination')

const FORECAST_PANEL_INSET = 400

/** Fit the view to every route whenever a new set of routes is shown. */
function FitBounds({ routes }: { routes: EvaluatedRoute[] }) {
  const map = useMap()
  useEffect(() => {
    const points = routes.flatMap((route) => route.geometry)
    if (points.length === 0) return
    const bounds = L.latLngBounds(points)
    if (!bounds.isValid()) return
    // On desktop the forecast panel floats over the map's right side; keep routes clear of it.
    const overlaid = window.matchMedia?.('(min-width: 1024px)').matches ?? false
    map.fitBounds(bounds, { paddingTopLeft: [32, 32], paddingBottomRight: [overlaid ? FORECAST_PANEL_INSET : 32, 32] })
  }, [map, routes])
  return null
}

function RouteMap({
  routes,
  origin,
  destination,
  selectedRouteId,
  selectedCheckpointIndex,
  onSelectRoute,
  onSelectCheckpoint,
  heatmap = null,
}: RouteMapProps) {
  const selectedRoute = routes.find((route) => route.id === selectedRouteId) ?? null
  // Draw the selected route last so it sits on top.
  const orderedRoutes = useMemo(
    () => [...routes].sort((a, b) => Number(a.id === selectedRouteId) - Number(b.id === selectedRouteId)),
    [routes, selectedRouteId],
  )

  return (
    <MapContainer
      className="route-map"
      center={[origin.latitude, origin.longitude]}
      zoom={7}
      scrollWheelZoom
      aria-label="Route map"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds routes={routes} />

      {heatmap && (
        // Below route lines (overlayPane z-index 400) and not interactive, so lines,
        // markers and popups stay clickable.
        <Pane name="weather-heatmap" style={{ zIndex: 350 }}>
          {heatmap.map((segment) => (
            <Polyline
              key={`heat-${segment.checkpointIndex}-${segment.state}`}
              positions={segment.positions}
              interactive={false}
              // className is a construction-time option in Leaflet (setStyle ignores it).
              className={`heatmap-segment heatmap-segment--${segment.state}`}
              pathOptions={{
                color: RISK_COLORS[segment.state],
                weight: 18,
                opacity: segment.state === 'unavailable' ? 0.55 : 0.45,
                dashArray: segment.state === 'unavailable' ? '6 10' : undefined,
                lineCap: 'butt',
              }}
            />
          ))}
        </Pane>
      )}

      {orderedRoutes.map((route) => {
        const style = routeStyle(route.provider_order)
        const selected = route.id === selectedRouteId
        return (
          <Polyline
            key={`${route.id}-${selected ? 'selected' : 'other'}`}
            positions={route.geometry}
            pathOptions={{
              color: style.color,
              dashArray: style.dashArray,
              weight: selected ? 7 : 4,
              opacity: selected ? 0.95 : 0.5,
            }}
            eventHandlers={{ click: () => onSelectRoute(route.id) }}
          >
            <Tooltip sticky>
              Route {route.provider_order + 1}
              {selected ? ' (selected)' : ' (click to select)'}
            </Tooltip>
          </Polyline>
        )
      })}

      <Marker position={[origin.latitude, origin.longitude]} icon={ORIGIN_ICON} title={`Origin: ${origin.label}`}>
        <Tooltip>Origin: {origin.label}</Tooltip>
      </Marker>
      <Marker
        position={[destination.latitude, destination.longitude]}
        icon={DESTINATION_ICON}
        title={`Destination: ${destination.label}`}
      >
        <Tooltip>Destination: {destination.label}</Tooltip>
      </Marker>

      {selectedRoute?.checkpoints.map((checkpoint) => {
        const state = checkpointRiskState(checkpoint)
        const active = checkpoint.index === selectedCheckpointIndex
        return (
          <CircleMarker
            key={`${selectedRoute.id}-${checkpoint.index}`}
            center={[checkpoint.latitude, checkpoint.longitude]}
            radius={active ? 10 : 7}
            pathOptions={{
              color: active ? '#111' : '#fff',
              weight: active ? 3 : 2,
              fillColor: RISK_COLORS[state],
              fillOpacity: 0.95,
              dashArray: state === 'unavailable' ? '3 3' : undefined,
            }}
            eventHandlers={{ click: () => onSelectCheckpoint(checkpoint.index) }}
          >
            <Tooltip>
              #{checkpoint.index}: {RISK_LABELS[state]}
            </Tooltip>
            <Popup>
              <CheckpointDetails
                checkpoint={checkpoint}
                routeLabel={`Route ${selectedRoute.provider_order + 1}`}
                compact
              />
            </Popup>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}

export default RouteMap
