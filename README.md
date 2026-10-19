# Weather-Aware Truck Routing

Web app that helps truck drivers pick safer routes by combining route alternatives,
weather forecasts along each route, cargo weight, and travel time.

- **Frontend:** React, TypeScript, Vite, Tailwind CSS v4, Leaflet / React Leaflet (`frontend/`)
- **Backend:** Python, Django, Django REST Framework (`backend/`)
- **Routing:** OpenRouteService (called from the backend only)
- **Weather:** Open-Meteo (no API key required)
- **Tests:** pytest, pytest-django

> Status: feature-complete for the assessment: risk engine, routing, weather, recommendation,
> route-planning UI with interactive map, checkpoint weather heatmap and 0–48 h forecast slider.

## Prerequisites

- Python 3.11+
- Node.js 20.19+ or 22.12+ (Vite requirement) and npm
- An [OpenRouteService API key](https://openrouteservice.org/dev/#/signup) (free tier is enough; needed for the route endpoint)

## Setup

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit values
python manage.py migrate

# Frontend (in a second terminal)
cd frontend
npm install
cp .env.example .env
```

Or from the repo root: `make install` (after copying both `.env` files).

## Environment variables

Each app reads its own `.env`. Templates: `backend/.env.example`, `frontend/.env.example`
(the root `.env.example` lists everything in one place for reference).

| Variable | App | Default | Purpose |
| --- | --- | --- | --- |
| `DJANGO_SECRET_KEY` | backend | dev-only key when `DJANGO_DEBUG=True`; **required** otherwise | Django cryptographic signing |
| `DJANGO_DEBUG` | backend | `False` | Debug mode. Set `True` locally |
| `DJANGO_ALLOWED_HOSTS` | backend | `localhost,127.0.0.1` | Comma-separated hostnames |
| `CORS_ALLOWED_ORIGINS` | backend | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated frontend origins |
| `ORS_API_KEY` | backend | empty | OpenRouteService key. **Server-side only**; route endpoint returns 503 without it |
| `ORS_BASE_URL` | backend | `https://api.openrouteservice.org` | ORS endpoint (override for a self-hosted instance) |
| `ORS_GEOCODE_COUNTRY` | backend | empty (worldwide) | Optional ISO country code (e.g. `US`, `PK`) limiting geocoding to one country |
| `OPEN_METEO_BASE_URL` | backend | `https://api.open-meteo.com` | Open-Meteo forecast API (no key needed) |
| `DJANGO_SECURE_SSL_REDIRECT` | backend | `False` | Redirect HTTP to HTTPS (production) |
| `DJANGO_SECURE_HSTS_SECONDS` | backend | `0` | HSTS max-age (production, HTTPS only) |
| `DJANGO_SECURE_PROXY_SSL_HEADER` | backend | `False` | Trust `X-Forwarded-Proto: https` from your proxy |
| `VITE_API_BASE_URL` | frontend | `http://localhost:8000/api` | Django API base URL |

Anything prefixed `VITE_` is bundled into the browser code, so never put secrets there.
The ORS key stays in `backend/.env`; the frontend reaches ORS only through the Django API.

## Operating region and timezone

- **Geocoding region:** origin/destination search and autocomplete are **worldwide by
  default**. Include the country in ambiguous names ("Lahore, Pakistan", "Paris, France",
  "Springfield, IL"). To limit search to one country, set `ORS_GEOCODE_COUNTRY` to its ISO code
  (e.g. `US` or `PK`) and restart the backend. With a filter active, "not found" and
  "ambiguous" errors name it ("Search is limited to country code US…").
- **Pakistan demo:** no setting needed. Use "City, Country" queries such as
  "Lahore, Pakistan" and "Islamabad, Pakistan" (optionally set `ORS_GEOCODE_COUNTRY=PK` to
  keep suggestions inside Pakistan). OpenRouteService routing and Open-Meteo forecasts work
  worldwide.
- **Units:** distances are in miles, weight in pounds, wind in mph, and rain and snowfall in
  inches/hour, matching the assessment's thresholds, in every region.
- **Departure timezone:** the departure is entered in the **browser's local timezone**. The
  form shows it with its UTC offset for the chosen date (e.g. "Asia/Karachi, UTC+05:00") and
  sends that offset to the API. ETAs and forecast hours are shown in the same local timezone.
  To plan a trip in a different timezone, set the computer or browser timezone accordingly;
  there is no separate trip-timezone picker.

## Run locally

```bash
# Terminal 1: API at http://localhost:8000
cd backend && source .venv/bin/activate && python manage.py runserver

# Terminal 2: UI at http://localhost:5173
cd frontend && npm run dev
```

Make equivalents: `make backend-run`, `make frontend-dev`.

Check the API: `curl http://localhost:8000/api/health/` → `{"status":"ok"}`.
The UI home page shows whether it can reach the backend.

## Tests and checks

```bash
cd backend && .venv/bin/pytest                    # backend tests
cd backend && .venv/bin/python manage.py check    # Django system checks
cd frontend && npm run lint && npm run build      # lint, type-check, production build
cd frontend && npm test                           # Vitest + Testing Library (jsdom)
```

`make test` runs all of the above.

The test suite never calls OpenRouteService or needs an API key. HTTP is stubbed
with `httpx.MockTransport` (see `backend/routes/tests/ors_fixtures.py`). Open-Meteo is
stubbed the same way, with payloads shaped like real responses
(`backend/weather/tests/open_meteo_fixtures.py`), so the whole suite runs offline.

## Project structure

```
backend/
  config/            Django project: settings, URLs, health endpoint
  routes/            ORS geocoding + directions, checkpoints, /api/routes/ endpoint
  weather/           Open-Meteo client, forecast-hour selection, 0–48 h forecast window API
  risk/              Weather risk classification, load restrictions
  tests/             pytest tests
  pytest.ini
  requirements.txt
frontend/
  src/api/           HTTP client for the Django API
  src/components/    Shared UI components
  src/features/routes/  Route planner: form, comparison, map, checkpoint details (+ tests)
  src/test/          Vitest setup and evaluation-response fixtures
  src/types/         Shared TypeScript types
```

## Frontend

`RoutePlanner` (`frontend/src/features/routes/`) calls `POST /api/routes/evaluate/` and shows:

- **Place autocomplete.** After 3 characters, the origin and destination fields suggest
  places from `GET /api/routes/locations/suggest/` (ORS autocomplete through the backend, so
  the key stays server-side). Typing is debounced (300 ms), superseded requests are cancelled,
  results are cached per query, and the list works with arrow keys, Enter, Escape or the mouse
  (ARIA combobox). Picking a suggestion only fills the field; the backend still geocodes the
  submitted text on evaluation, and the exact-label rule resolves a picked label. If
  suggestions are unavailable (e.g. no ORS key), the field works as plain text.
- **Trip form.** Origin, destination, departure, weight (1–150,000 lb) and checkpoint interval.
  The departure comes from a `datetime-local` input in the browser's timezone. It is sent with
  that timezone's UTC offset for the chosen date (DST-aware) and never assumed to be UTC.
  Field errors from the client and from the server (DRF 400) appear next to the inputs. The
  submit button is disabled while a request runs. Requests time out after 90 s.
- **Errors vs. results.** Request failures (validation, location not found or ambiguous,
  provider errors, timeouts, network) show as red "Evaluation failed" alerts and keep the
  entered values. For an ambiguous location, the backend's candidates can be clicked to fill
  the matching field. A successful evaluation with no safe route is shown as a result, not an
  error.
- **Route comparison.** One card per backend route: distance, duration, Severe, High and No
  Travel miles, average risk, backend rank and status (Safe / Unsafe: No Travel / Not fully
  evaluated). "Recommended" appears only when `recommendation_status` is `recommended`, meaning
  every route was evaluated. If any route lacks weather, the best evaluated route gets a
  "Provisional pick" badge, the banner says "Provisional: … safest of the fully evaluated
  routes", and a warning names the routes that could not be evaluated.
- **Map** (Leaflet + OpenStreetMap tiles). Every route's real geometry is drawn, with colour
  plus dash pattern per route. The selected route is thicker. A and B markers show origin and
  destination. Checkpoint circles on the selected route are coloured by risk and show a text
  tooltip and a details popup. Missing-weather checkpoints are grey and dashed. Clicking a line
  or card selects the route; clicking a marker or list row selects the checkpoint.
- **Checkpoint details.** Distance, ETA and forecast hour in the user's timezone, wind, rain
  and snowfall values with each hazard's risk, overall risk, any load-rule escalation, and the
  reason when weather is unavailable ("Weather unavailable", never "Low").

The frontend never ranks routes or applies thresholds: all values come from the API. Risk is
always shown as text plus a symbol, not colour alone.

Tests (`npm test`) mock the API client. In planner tests the Leaflet map is replaced by a stub
with the same props, so route and checkpoint selection can be tested. A separate smoke test
renders the real Leaflet map in jsdom (lines, markers, attribution, missing-weather styling).
jsdom has no real layout, so panning, zooming, popups and fit-to-bounds are verified in the
browser rather than in tests.

### Weather heatmap and forecast slider

**What it shows:** forecast risk at a **selected hour** (departure + 0…48 h, 1-hour steps)
at every checkpoint of the selected route. It is not the trip ETA view: the comparison
cards, checkpoint list and checkpoint markers keep showing conditions at each checkpoint's
own ETA. It is also not radar or a gridded weather field.

**Where the data comes from:** the evaluation response only holds one forecast hour per
checkpoint (the hour nearest its ETA), so it cannot drive a 0–48 h slider. When the
heatmap is first switched on, the frontend sends the evaluation's distinct checkpoint
coordinates, departure time and load to `POST /api/weather/forecast-window/`. The backend
returns, for each location and each of the 49 hourly slots, the real Open-Meteo forecast and
risk. It uses the same client, the same nearest-hour policy (±30 min) and the same risk
engine (load rules included) as route evaluation. That happens once per evaluation; moving
the slider or switching routes makes no further requests.

**Time selection:** slot *h* targets `departure + h hours` (elapsed time, so DST-safe). The
forecast hour actually used is shown under the slider and in the table. A departure at 07:40
uses 08:00, 09:00, … (nearest hour, ties go to the later hour). Slots beyond Open-Meteo's
~16-day horizon have no data: they are shown as "Weather unavailable" and the panel says how
many hours are affected.

**Drawing:** each stretch of the selected route takes the colour of its **nearest
checkpoint**, split halfway between consecutive checkpoints. This is the same allocation the
backend uses for risk miles. Nothing is interpolated between checkpoints, so conditions there
may differ. Stretches are wide translucent lines in their own map pane beneath the route lines.
They are not clickable, so lines, markers, popups and zoom stay usable. Missing data is grey
and dashed, never Low.

**Accessibility:** the legend lists all six states (Low, Moderate, High, Severe, No Travel,
Weather unavailable) with symbols. A collapsible table gives the same data as text
(checkpoint, mile, forecast hour, wind, rain, snow, risk or unavailable reason). The slider
supports arrow keys (1 h) and announces "+N h, local date and time".

**Limits:**
- At most 300 distinct checkpoint locations per request. Use a larger interval for very long trips.
- Nearby checkpoints (~1 km) share one forecast, as in route evaluation.
- The response is roughly 15 KB per location.
- Values are model forecasts, not observations. Accuracy declines with lead time; that matters more for multi-day horizons than within 48 hours.

`POST /api/weather/forecast-window/` request:

```json
{"locations": [{"latitude": 32.7767, "longitude": -96.797}],
 "departure_time": "2026-10-19T07:40:00-05:00", "load_weight_lbs": 42000}
```

Response (abbreviated): `slots` has 49 entries of `{offset_hours, target_time, forecast_time}`,
and `locations[]` has one entry per request location, in order, each with 49 `observations`
of `{weather, risk}` (the same objects as evaluation checkpoints). There is also
`coverage_note`. Invalid input returns 400. Weather-provider failures return 200 with
unavailable observations.

## Risk model

Pure Python, no Django or database dependencies: `backend/risk/`.

| Module | Responsibility |
| --- | --- |
| `levels.py` | `RiskLevel` enum and the averaging score map |
| `engine.py` | Weather thresholds, input validation, checkpoint risk with load rules |
| `summary.py` | Distance-weighted route summary |
| `recommendation.py` | Safe-route filtering and ranking |

### Weather thresholds

| Level | Wind (mph) | Rain (in/hr) | Snow (in/hr) |
| --- | --- | --- | --- |
| Low | < 25 | < 0.10 | < 0.5 |
| Moderate | 25 to < 35 | 0.10 to < 0.25 | 0.5 to < 1.0 |
| High | 35 to < 45 | 0.25 to < 0.50 | 1.0 to < 2.0 |
| Severe | 45 to < 55 | 0.50 to ≤ 1.00 | 2.0 to ≤ 3.0 |
| No Travel | ≥ 55 | > 1.00 | > 3.0 |

**Assumption:** the assessment's ranges touch or overlap at some boundaries. Each boundary
value belongs to the higher band (e.g. wind 35 mph is High), except that the Severe band for
rain and snow includes its upper bound (rain 1.00 in/hr is Severe; No Travel starts above it).

Measurements and load weight must be finite and non-negative. NaN, ±infinity, negatives and
non-numbers are rejected with an error, never coerced to zero.

### Checkpoint risk

1. Classify wind, rain and snow independently (all three are kept for display).
2. Base risk = the highest of the three.
3. Load rules (on wind only):
   - wind ≥ 55 mph → No Travel for any load;
   - wind ≥ 45 mph and load > 30,000 lb → No Travel;
   - wind ≥ 35 mph and load > 40,000 lb → at least Severe.

`load_restriction` records when a load rule raised the level above the weather-only risk.

### Route summary

**Segment allocation:** checkpoints are sample points, not equal road segments. Each
checkpoint represents the miles closer to it than to any other checkpoint: from the
midpoint with the previous checkpoint to the midpoint with the next (the origin and
destination checkpoints cover only their inner half-gap). Every mile is counted once and
the segment lengths sum to the route distance. Checkpoints must start at mile 0, increase
strictly, and end within 0.01 mi of the route distance.

**Risk score** for the distance-weighted average: Low = 0, Moderate = 1, High = 2,
Severe = 3. No Travel has **no** score: a route with any No Travel segment is marked unsafe
(`has_no_travel`), its No Travel miles are reported separately, and its average risk is
`None` instead of a number that could look acceptable.

Summary fields: `severe_miles`, `high_miles`, `no_travel_miles`, `average_risk_score`,
`total_distance_miles`, `duration_seconds`, `has_no_travel`, `segments`.

### Recommendation

Routes with No Travel conditions are removed from the candidate pool. Safe routes are
sorted lexicographically, in this order:

1. fewest Severe miles
2. fewest High miles
3. lowest average risk
4. shortest duration

There is no weighted sum, so a faster route can never beat one with fewer Severe miles.
Before comparing, miles are rounded to 0.01, average risk to 0.001 and duration to whole
seconds, so floating-point noise cannot reorder routes. Remaining exact ties keep the
provider's order. If every route is unsafe, `recommended` is `None` and the result reports
that no safe route is available.

## Routing (OpenRouteService)

Backend `routes` app:

| Module | Responsibility |
| --- | --- |
| `ors.py` | ORS HTTP client: geocoding and `driving-hgv` directions, timeouts, error mapping |
| `geocoding.py` | Picks one confident match per location or reports ambiguity |
| `geometry.py` | Haversine distances, great-circle interpolation along the polyline |
| `checkpoints.py` | Checkpoint distances, positions and baseline ETAs |
| `services.py` | Orchestrates geocode → directions → checkpoints |
| `serializers.py`, `views.py` | Request validation and JSON response |

### Configuration

1. Sign up at <https://openrouteservice.org/dev/#/signup> and create a token.
2. Put it in `backend/.env` as `ORS_API_KEY=...` and restart the server.

The key is sent to ORS only in the `Authorization` header. It never appears in URLs,
API responses, error messages or logs, and the frontend never sees it.

### `POST /api/routes/candidates/`

```bash
curl -s -X POST http://localhost:8000/api/routes/candidates/ \
  -H "Content-Type: application/json" \
  -d '{"origin": "Dallas, TX", "destination": "Houston, TX",
       "departure_time": "2026-10-19T08:00:00-05:00",
       "checkpoint_interval_miles": 50, "load_weight_lbs": 42000}'
```

| Field | Rule |
| --- | --- |
| `origin`, `destination` | Non-blank text, ≤ 200 chars |
| `departure_time` | ISO 8601 **with** timezone offset (`-05:00` or `Z`). Naive times are rejected, not assumed UTC |
| `checkpoint_interval_miles` | `10`, `25` or `50` |
| `load_weight_lbs` | Positive finite number. Validated and echoed; does not affect routing yet |

Response `200` (abbreviated; values are illustrative):

```json
{
  "origin": {"query": "Dallas, TX", "label": "Dallas, TX, USA", "latitude": 32.7767, "longitude": -96.797},
  "destination": {"query": "Houston, TX", "label": "Houston, TX, USA", "latitude": 29.7604, "longitude": -95.3698},
  "departure_time": "2026-10-19T08:00:00-05:00",
  "checkpoint_interval_miles": 50,
  "load_weight_lbs": 42000.0,
  "requested_route_count": 3,
  "route_count": 3,
  "alternatives_note": "OpenRouteService only calculates alternative routes for trips up to about 100 km (62 miles), so the alternatives were found by routing through points on either side of the direct line.",
  "routes": [
    {
      "id": "route-1",
      "provider_order": 0,
      "distance_miles": 239.412,
      "duration_seconds": 13020.4,
      "geometry": [[32.7767, -96.797], [32.7701, -96.7932]],
      "checkpoints": [
        {"index": 0, "distance_miles": 0.0, "latitude": 32.7767, "longitude": -96.797,
         "elapsed_seconds": 0.0, "eta": "2026-10-19T08:00:00-05:00"},
        {"index": 1, "distance_miles": 50.0, "latitude": 32.1521, "longitude": -96.4683,
         "elapsed_seconds": 2719.2, "eta": "2026-10-19T08:45:19.200000-05:00"}
      ]
    }
  ]
}
```

Units: miles, seconds, decimal degrees. `geometry` and checkpoints use `[latitude, longitude]`,
the order Leaflet expects (ORS returns `[longitude, latitude]`; the backend swaps them).
The request context (origin, destination, departure, interval, load) is returned once at
the top level and applies to every route.

Errors return `{"error": {"code", "message", "query"?, "candidates"?}}`. For geocoding errors, `query` is the origin or destination text that failed:

| Status | `code` | When |
| --- | --- | --- |
| 400 | DRF field errors | Invalid or missing request fields |
| 422 | `location_not_found` | No confident geocoding match (`candidates` lists weak matches, if any) |
| 422 | `ambiguous_location` | Several equally plausible matches; `candidates` lists them |
| 422 | `same_location` | Origin and destination resolve to the same place |
| 422 | `route_not_found` | ORS found no drivable truck route |
| 422 | `route_too_long` | Route exceeds ORS distance limits |
| 502 | `routing_unavailable`, `routing_auth_failed`, `routing_rate_limited`, `routing_quota_exceeded`, `invalid_route_data` | Provider failure or unusable response |
| 503 | `routing_not_configured` | `ORS_API_KEY` is not set |
| 504 | `routing_timeout` | ORS did not respond (5 s connect / 20 s read) |

### Geocoding

The backend sends free text to ORS geocoding (worldwide, or limited to `ORS_GEOCODE_COUNTRY` if set)
and requests up to 5 matches. It uses a match only if its confidence is ≥ 0.8 **and** it
leads the next distinct match by ≥ 0.1. A tie is broken only when exactly one confident
candidate's label equals the query text, ignoring case and spacing. For example,
"Islamabad, Pakistan" ties with other places named Islamabad, and this rule is what lets a
suggestion picked in the UI resolve. Otherwise it returns `ambiguous_location` with the
candidates instead of guessing. Limitations: bare city names ("Springfield") are often
ambiguous, so use "City, State". Confidence scores come from the provider and are not
calibrated. A city resolves to its centroid, not to a truck-accessible address.

### Alternative routes

The backend requests up to three alternatives from the `driving-hgv` profile and returns
only the routes ORS actually produced, in provider order (`route-1` is the provider's
primary route). The public ORS API calculates alternatives only for trips up to about
100 km. For longer trips ORS rejects the request (error 2004). The backend then:

1. fetches the single best route without alternatives;
2. requests detour routes forced through a **via point**: the midpoint of the straight
   origin–destination line pushed sideways by 15 %, then 30 %, of the straight-line
   distance, alternating left and right (at most 4 extra requests). The via point may snap
   to any nearby road (unlimited snapping radius);
3. keeps a detour only if it is at most 1.5× the best route's distance and less than 80 % of
   it lies within 1 mile of an already accepted route, until three routes exist.

A detour ORS cannot route is skipped; a rate-limit, quota or timeout error stops the search
and keeps the routes found so far. `alternatives_note` says that detours were used, or that
fewer than three distinct routes were found. Checked live on 2026-10-19: Dallas → Houston,
Denver → Salt Lake City and Chicago → Atlanta each returned three distinct routes in 2–3 s.

### Provider quota

Successful geocoding and autocomplete answers are cached for 24 hours (Django's default
in-process cache) to spare the free ORS quota. When ORS reports `Quota exceeded` (HTTP 403
or 429), the API returns `routing_quota_exceeded` and the UI shows "Routing service daily
limit reached" instead of a credentials error. The free quota resets at 00:00 UTC.

### Checkpoints and ETAs

- Checkpoints sit at mile 0, at every interval strictly before the destination, and at the
  destination's exact route distance. A route whose length is an exact multiple of the
  interval gets no duplicate. A route shorter than the interval gets only origin and destination.
- Positions are interpolated along the route polyline by cumulative great-circle (haversine)
  distance, not by vertex index. Within a segment the position follows the great circle. ORS's
  route distance and the polyline's geometric length differ slightly, so a checkpoint at
  *d* miles is placed at the same fraction *d / total* of the polyline.
- **ETA baseline:** `eta = departure + duration × (d / total)`, i.e. a constant average
  speed over the whole route, in the departure's timezone offset. It does **not** model rest
  stops, hours-of-service breaks, traffic changes or speed differences between road types.
- Checkpoint distances meet the risk summary's rules (start at 0, strictly increasing, end
  at the route distance).

## Weather evaluation (Open-Meteo)

| Module | Responsibility |
| --- | --- |
| `weather/open_meteo.py` | HTTP client: batched requests, timeouts, response-shape and unit validation |
| `weather/forecast.py` | Forecast window, ETA → forecast-hour selection, normalized weather |
| `routes/evaluation.py` | Checkpoint forecasts → risk engine → route summaries → recommendation |

### Variables and units

Requested from `GET https://api.open-meteo.com/v1/forecast` with `wind_speed_unit=mph`,
`precipitation_unit=inch`, `timeformat=unixtime` (UTC) and `timezone=GMT`. No API key is needed
for non-commercial use.

| Open-Meteo variable | Meaning (per Open-Meteo docs) | Used as |
| --- | --- | --- |
| `wind_speed_10m` | Wind speed at 10 m, instant value | `wind_speed_mph` |
| `rain` | Rain total of the **preceding hour**, inches | `rain_in_per_hr` (1-hour total = hourly rate) |
| `snowfall` | Snowfall **depth** of the preceding hour, inches (not water equivalent) | `snowfall_in_per_hr` |

The client checks `hourly_units` on every response (`mp/h`, `inch`, `inch`) and rejects any
other unit rather than converting. For example, without `precipitation_unit=inch` Open-Meteo
reports snowfall in `cm`. Snowfall is used as snow depth per hour, which is what the risk
thresholds describe. It is never treated as liquid-water equivalent (Open-Meteo: about 7 cm
snow ≈ 10 mm water).

### Which forecast hour a checkpoint gets

- Each checkpoint uses its own **ETA**, not the departure time. All comparisons are in UTC.
- The forecast hour **nearest** to the ETA is used. On an exact half-hour tie the later hour
  wins, because rain and snowfall at hour *T* describe the hour ending at *T*, which then
  contains the ETA.
- The chosen hour must be within **30 minutes** of the ETA. Otherwise the checkpoint is
  `outside_forecast_coverage`. The backend never reaches further back or forward for an unrelated hour.

### Efficiency

All checkpoints of all routes are collected first. Checkpoints that round to the same
0.01° (~1.1 km; finer than the forecast grid) share one location, which covers the shared
origin, destination and overlapping stretches. One forecast window (first ETA hour to last
ETA hour) is used for every location. Locations go to Open-Meteo in batches of 50
coordinates per request, with at most 4 concurrent requests, a 5 s connect timeout and a
15 s read timeout. There is no caching.

**Retries.** Open-Meteo counts every location against its per-minute limit, and the 0–48 h
heatmap request usually follows route evaluation straight away, so a batch can be refused
(HTTP 429) or fail briefly. Timeouts, connection errors, HTTP 429 and 5xx are retried twice,
after 1 s and then 2 s. A `Retry-After` of up to 5 s is honoured instead; a longer one is not
waited for. Other 4xx answers are not retried. Only when every attempt fails are that batch's
locations reported as unavailable (`provider_error`), never as zero or Low.

### Forecast coverage

Open-Meteo serves hourly forecasts up to **16 days ahead** (UTC calendar days). The
requested window is clipped to that horizon. Checkpoints whose ETA falls beyond it are
marked `outside_forecast_coverage`. If the whole trip is beyond it, no weather request is
made. Forecast skill also drops well before day 16, so treat late-horizon results as
indicative.

### Missing data is never safe

- Null, absent, non-numeric, NaN, infinite or negative provider values are **unavailable**,
  never zero. Explicit `0.0` values are zero.
- A checkpoint without usable weather gets `weather.status = "unavailable"` with a `reason`
  (`outside_forecast_coverage`, `missing_values`, `provider_error`, `invalid_provider_data`)
  and `risk: null`.
- A route with **any** such checkpoint is `evaluation_status = "weather_unavailable"`. It gets
  no summary and no rank, it is listed in `not_recommended` with the reason, and it can never
  be recommended.
- The recommendation is chosen only among fully evaluated routes, using the existing
  ranking (Severe miles → High miles → average risk → duration, ties in provider order).
  If none qualify, the message says why (No Travel conditions, missing forecasts, or both).
- Weather outages do not fail the request. The response is `200` with
  `weather_status: "unavailable"` and an explanatory `weather_note`.

### Recommendation status (safety policy)

| `recommendation_status` | `comparison_conclusive` | Meaning |
| --- | --- | --- |
| `recommended` | `true` | Every route fully evaluated; `recommended_route_id` is the safest |
| `provisional` | `false` | Some routes lack weather; `recommended_route_id` is only the safest **of the fully evaluated routes**. The overall comparison is inconclusive |
| `no_safe_route` | `true` | Every route fully evaluated and every route contains No Travel |
| `inconclusive` | `false` | No fully evaluated safe route, and some routes lack weather |

`safe_route_available` means a fully evaluated, safe route exists. That route may still be
only a provisional pick. The UI shows "Recommended" only for `recommended`, shows "Provisional
pick" plus an inconclusive warning for `provisional`, and never shows a route that is
unevaluated or contains No Travel as safe.

### `POST /api/routes/evaluate/`

The request body is identical to `/api/routes/candidates/`. The response contains every
candidates field, plus the following (abbreviated; values are illustrative):

```json
{
  "weather_status": "complete",
  "weather_note": null,
  "recommended_route_id": "route-1",
  "safe_route_available": true,
  "recommendation_message": "Recommended route: route-1.",
  "recommendation_status": "recommended",
  "comparison_conclusive": true,
  "ranking": ["route-1"],
  "not_recommended": [
    {"route_id": "route-2", "reasons": [{"code": "no_travel", "message": "Contains 12.4 miles of No Travel conditions."}]}
  ],
  "routes": [
    {
      "id": "route-1", "provider_order": 0, "distance_miles": 239.412, "duration_seconds": 13020.4,
      "geometry": [[32.7767, -96.797]],
      "evaluation_status": "evaluated",
      "rank": 1,
      "summary": {"severe_miles": 0.0, "high_miles": 18.5, "no_travel_miles": 0.0, "average_risk_score": 0.412,
                  "total_distance_miles": 239.412, "duration_seconds": 13020.4, "has_no_travel": false, "is_safe": true},
      "checkpoints": [
        {"index": 1, "distance_miles": 50.0, "latitude": 32.1521, "longitude": -96.4683,
         "elapsed_seconds": 2719.2, "eta": "2026-10-19T08:45:19.200000-05:00",
         "weather": {"status": "available", "reason": null, "message": null,
                     "forecast_time": "2026-10-19T14:00:00+00:00",
                     "wind_speed_mph": 27.3, "rain_in_per_hr": 0.12, "snowfall_in_per_hr": 0.0},
         "risk": {"wind": "moderate", "rain": "moderate", "snow": "low", "base": "moderate",
                  "overall": "moderate", "load_restriction": "none"}}
      ]
    }
  ]
}
```

| Field | Values |
| --- | --- |
| `weather_status` | `complete` (all checkpoints have weather), `partial`, `unavailable` (none) |
| `routes[].evaluation_status` | `evaluated`, `weather_unavailable` |
| `risk.*` levels | `low`, `moderate`, `high`, `severe`, `no_travel` |
| `risk.load_restriction` | `none`, `heavy_load_wind_severe`, `heavy_load_wind_no_travel` |
| `not_recommended[].reasons[].code` | `no_travel`, `weather_unavailable` |

Routing errors (geocoding, ORS) return the same sanitized error bodies as the candidates endpoint.

## Deployment

The two apps deploy as **separate Vercel projects** (Root Directory `backend/` and
`frontend/`). Django is detected automatically from `manage.py` / `config.wsgi`.

### Backend on Vercel

1. In the Vercel dashboard: **Add New Project** → import this repo → set
   **Root Directory** to `backend` → Framework Preset should be Django.
2. Set environment variables (Production + Preview as needed):

   | Variable | Example |
   | --- | --- |
   | `DJANGO_SECRET_KEY` | long random string |
   | `DJANGO_DEBUG` | `False` |
   | `DJANGO_ALLOWED_HOSTS` | your custom API host, if any (`.vercel.app` deployment URL is added automatically via `VERCEL_URL`) |
   | `CORS_ALLOWED_ORIGINS` | `https://your-frontend.vercel.app` (exact frontend origin, no trailing slash) |
   | `ORS_API_KEY` | OpenRouteService token |
   | `ORS_GEOCODE_COUNTRY` | empty for worldwide, or e.g. `US` / `PK` |
   | `DJANGO_SECURE_SSL_REDIRECT` | `true` (optional) |
   | `DJANGO_SECURE_HSTS_SECONDS` | `31536000` (optional) |

   `DJANGO_SECURE_PROXY_SSL_HEADER` defaults to on when `VERCEL=1`. SQLite lives under
   `/tmp` and is migrated on cold start (built-in Django tables only; no domain persistence).
3. Deploy. `backend/vercel.json` sets `maxDuration` to 300 s so long evaluations can finish.
4. Smoke-test: `curl https://<api>.vercel.app/api/health/` → `{"status":"ok"}`.

Or from the CLI (Root Directory = `backend`):

```bash
cd backend
vercel          # first time: link / create project
vercel env add  # or set vars in the dashboard
vercel --prod
```

**Alternative: any host with Python 3.11+** (gunicorn):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# same env vars as above, plus DJANGO_SECURE_PROXY_SSL_HEADER=true behind TLS proxy
.venv/bin/python manage.py migrate
.venv/bin/python manage.py check --deploy
.venv/bin/gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 3 --timeout 120
```

- Keep proxy / function timeouts ≥ 120 s (evaluations call ORS and Open-Meteo sequentially).
- The API serves JSON only. Admin and static files are not needed for the product UI.
- With HTTPS enabled, `check --deploy` still reports W005 and W021 (HSTS include-subdomains
  and preload). Those are domain-wide policy choices, left to the operator.

### Frontend on Vercel

1. Separate Vercel project, **Root Directory** `frontend`.
2. Set `VITE_API_BASE_URL=https://<your-backend>.vercel.app/api` (baked in at build time).
3. Redeploy the frontend after the backend URL is known. Update the backend
   `CORS_ALLOWED_ORIGINS` to match the frontend origin.

```bash
cd frontend
npm ci
VITE_API_BASE_URL=https://api.your-domain/api npm run build
# or: vercel --prod  (with VITE_API_BASE_URL set in the project env)
```

**Checklist:**
- [ ] Backend env set; `DJANGO_DEBUG=False`; new secret key; health check returns ok
- [ ] `CORS_ALLOWED_ORIGINS` = exact frontend origin(s); custom hosts in `DJANGO_ALLOWED_HOSTS` if used
- [ ] `ORS_API_KEY` set as a server secret (never as a `VITE_` variable); `ORS_GEOCODE_COUNTRY` empty (worldwide) or set to the operating country
- [ ] Frontend built with the production `VITE_API_BASE_URL`; served over HTTPS
- [ ] Function / proxy timeouts ≥ 120 s (Vercel backend uses 300 s via `vercel.json`)
- [ ] Live verification below completed against the deployed URLs

## Live verification (needs an ORS key)

The automated tests never call ORS or Open-Meteo. Without a key, `/api/routes/candidates/`
and `/api/routes/evaluate/` return `503 {"error": {"code": "routing_not_configured", ...}}`
and the UI shows "Routing is not configured on the server". `/api/weather/forecast-window/`
needs no key.

1. Get a free token at <https://openrouteservice.org/dev/#/signup>, add `ORS_API_KEY=<token>`
   (and optionally `ORS_GEOCODE_COUNTRY`) to `backend/.env`, and restart `runserver`.
2. Short trip (alternatives are only offered under ~100 km):

   ```bash
   curl -s -X POST http://localhost:8000/api/routes/evaluate/ -H "Content-Type: application/json" \
     -d '{"origin":"Waco, TX","destination":"Temple, TX","departure_time":"<ISO with offset, within 16 days>",
          "checkpoint_interval_miles":10,"load_weight_lbs":42000}'
   ```

   Expect `weather_status: "complete"` and `recommendation_status: "recommended"`. ORS may
   return 1–3 routes; on 2026-10-19 it returned 1 route for Waco → Temple and 3 for
   Dallas, TX → Fort Worth, TX.
3. Long trip (e.g. Dallas, TX → Houston, TX): expect 3 routes and an `alternatives_note`
   (ORS rejects the alternatives request with error 2004; the backend builds via-point detours).
4. Pakistan (worldwide default, or `ORS_GEOCODE_COUNTRY=PK`): "Lahore, Pakistan" → "Islamabad, Pakistan".
5. Inconclusive state: depart about 2 hours before the forecast horizon ends (today UTC + 16 days,
   23:00 UTC). Expect later checkpoints `outside_forecast_coverage` and `recommendation_status: "inconclusive"`.
6. UI: evaluate, select routes and checkpoints, open popups, turn the heatmap on, move the
   slider, try an ambiguous name ("Springfield"), and check the mobile
   and desktop layouts.

## Known limitations

- Public ORS calculates alternative routes only for trips under ~100 km. Longer trips get
  via-point detours instead, which are heuristic: they may be noticeably longer than the
  best route and are not guaranteed to exist (then fewer than three routes are shown).
- ORS requests use the `driving-hgv` profile without vehicle dimensions or weight, so load
  weight affects risk, not routing.
- ETAs assume constant average speed (no stops, breaks or traffic changes).
- Forecasts are Open-Meteo model forecasts, hourly, up to ~16 days ahead, and are not
  guaranteed to be accurate. The heatmap shows checkpoint forecasts, not radar or observations.
- Text geocoding can be ambiguous; confidence thresholds are heuristics.
- Evaluation can take tens of seconds (sequential geocoding, then routing, then batched weather).
- Autocomplete calls count against the ORS geocoding quota (one request per debounced query of
  at least 3 characters).
- No authentication or rate limiting, and only geocoding is cached (per process). Public
  deployments should add rate limiting at the proxy to protect the ORS and Open-Meteo quotas.
- Tests need `backend/.env` (or env vars) with a secret key or `DJANGO_DEBUG=True`, because
  the settings refuse to start in production mode without a secret key.

## API

| Method | Path | Response |
| --- | --- | --- |
| GET | `/api/health/` | `{"status": "ok"}` |
| GET | `/api/routes/locations/suggest/?q=` | Up to 5 place suggestions (`{query, suggestions: [{label, latitude, longitude}]}`); fewer than 3 characters returns none without calling ORS |
| POST | `/api/routes/candidates/` | Route alternatives with checkpoints (see above) |
| POST | `/api/routes/evaluate/` | Candidates + checkpoint weather, risk, summaries, recommendation |
| POST | `/api/weather/forecast-window/` | Hourly forecast + risk at given locations, 0–48 h after departure (no ORS key needed) |
