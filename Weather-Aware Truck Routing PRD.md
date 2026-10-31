# Weather-Aware Truck Routing: Product Requirements Document

Prepared for AJ Shahin · Version 1.1 · October 31, 2026 · Source: Spotter Full Stack Developer assessment

**v1.1 changes.** Load weight now means cargo weight with no hard cap; wind load rules use continuous bands; Blocked routes are flagged as a client-approval assumption; average risk has a formula; route generation requests 3 and returns up to 3; added error handling (4.11), acceptance criteria (7.1), and client questions (10.1).

## 1. Overview

**Product.** A React + Django web app that helps a truck driver pick the safest of three routes by combining the weather forecast along each route, the load weight, and the travel time. Weather is sampled at checkpoints using the truck's estimated arrival time (ETA) at each point, classified with the brief's risk and load rules, rolled up per route, and turned into a recommendation. A weather heatmap with a 0–48 hour slider shows conditions across the whole trip corridor.

**Goal.** The best possible submission against the brief: correct and explainable risk logic, a fast and smooth map and heatmap, clean code, and clear documentation. The brief says to prioritize correctness and clarity over extra features, so every P1/P2 item below exists only to lift a scored area.

**Priority legend.** P0 = required by the brief or needed for correctness. P1 = polish that directly lifts a scored area. P2 = stretch, only after P0 and P1 are stable.

**Build order inside P0.** Correctness first: routing, checkpoints and ETA, weather, risk engine, recommendation. Then the map and a basic heatmap. Then smoothness tuning, which still ships because the heatmap is scored on smoothness. P1 and P2 start only after that.

| Weight | Scored area | What wins it |
| --- | --- | --- |
| 40% | Routes, weather, risk and recommendation logic | Exact rule implementation, ETA-aligned weather, deterministic ranking, boundary tests, plain-language explanations |
| 40% | UI, map and heatmap smoothness and performance | 60 fps slider scrubbing with zero refetch, fast first result, clear visual hierarchy |
| 15% | Code quality | Pure engine modules, typed, linted, tested, CI |
| 5% | Documentation and walkthrough | README, assumptions, API docs, 5–10 min Loom |

**Non-goals.** Building a routing engine, live traffic, driver hours-of-service planning, user accounts, replacing the brief's ranking order with a custom weighted score.

## 2. Brief-to-PRD traceability (nothing missed)

| Brief requirement | PRD items |
| --- | --- |
| User enters origin and destination | IN-1, GC-1 to GC-3 |
| User enters departure date/time | IN-2, CP-5 |
| User enters load weight | IN-3, RK-2 |
| Generate 3 route options using a routing API | RT-1 to RT-5 |
| Sample weather every 10 / 25 / 50 miles at the truck's ETA | IN-4, CP-1 to CP-4, WX-1 to WX-6 |
| Calculate weather risk using the provided risk and load rules | RK-1 to RK-6 |
| Recommend the best route, balancing risk and travel time | SC-1 to SC-6 |
| Show routes, checkpoints, risk levels, ETAs, summaries on a map | MP-1 to MP-8 |
| Weather heatmap along the corridor with 0–48 h slider | HM-1 to HM-10 |
| Third-party APIs allowed, no routing engine needed | Section 5 |
| Deliverables: GitHub repo, hosted app, 5–10 min Loom | Section 8 |
| Evaluation weights, correctness over extras | Sections 1, 7 |

## 3. User and core flow

**User.** A truck driver or dispatcher planning a trip who needs to know which route avoids dangerous wind, rain, or snow for their specific load, at the time they will actually be there.

**Flow.** (1) Enter origin, destination, departure time, load weight, and checkpoint interval. (2) Submit. (3) See three routes on the map with a recommended one highlighted and a one-line reason. (4) Compare route cards (time, risk breakdown, tradeoffs). (5) Click a route or checkpoint to see ETA, weather values, and why it got its risk level. (6) Scrub the 0–48 h heatmap slider to see how conditions evolve across the corridor.

## 4. Functional requirements

### 4.1 Trip input

| ID | Requirement | Pri |
| --- | --- | --- |
| IN-1 | Origin and destination fields with autocomplete (debounced, keyboard navigable) and a swap button | P0 |
| IN-2 | Departure date/time picker. Default is now rounded up to the next 15 min. Interpreted in the origin's local timezone, stored as UTC. Validate: not more than 1 h in the past, within the forecast horizon | P0 |
| IN-3 | Load weight (cargo, as entered) in lb with an lb/kg toggle. Validate greater than 0 and show a soft warning above 80,000 lb (typical US gross limit) without blocking, because cargo versus gross weight is unconfirmed (see 10.1). Quick presets (20,000 / 35,000 / 45,000 / 80,000) so reviewers can trigger the 30,000 and 40,000 lb rules instantly | P0 |
| IN-4 | Checkpoint interval selector: 10, 25, or 50 miles (default 25) | P0 |
| IN-5 | Inline validation, submit disabled while invalid, last inputs remembered, inputs encoded in URL query params so a trip is shareable | P1 |
| IN-6 | One-click sample trips (for example Chicago to Denver, Dallas to Oklahoma City) | P1 |
| IN-7 | Advanced options: gust-aware wind toggle, truck dimensions (height, length) passed to the routing API | P2 |

### 4.2 Geocoding

| ID | Requirement | Pri |
| --- | --- | --- |
| GC-1 | Provider-backed autocomplete (a provider whose terms allow type-ahead, not public Nominatim), US-biased, results cached | P0 |
| GC-2 | Backend geocode endpoint so API keys never reach the browser | P0 |
| GC-3 | Clear handling of no results, ambiguous results, and origin equal to destination | P0 |
| GC-4 | Checkpoint place labels such as 'Mile 125 · near Cheyenne, WY' using an offline US places dataset with nearest-neighbour lookup, avoiding hundreds of reverse-geocode calls | P1 |

### 4.3 Route generation

| ID | Requirement | Pri |
| --- | --- | --- |
| RT-1 | Request 3 route options from a routing API using a truck/heavy-vehicle profile and return up to 3 sufficiently distinct routes (see RT-2). Load weight is passed as vehicle weight only where the provider supports it | P0 |
| RT-2 | Guarantee distinct routes: drop any route whose geometry overlaps another by more than about 90%. If the provider returns fewer than 3, request variants via forced via-waypoints or a secondary provider. If still fewer than 3, show what exists and explain why | P0 |
| RT-3 | Per route: id, label (Fastest, Shortest, Alternative), geometry, distance in miles, duration, and per-section durations used for ETA | P0 |
| RT-4 | Route summary: main highways ('via I-80 W, I-76 W'), distance, duration, arrival time | P0 |
| RT-5 | Provider adapter interface so the routing vendor can be swapped. Phase 0 gate: before building on a provider, confirm heavy-vehicle routing, alternative routes, weight restrictions, geometry with section durations, and free-tier limits. Candidates: HERE Routing v8 (truck mode, multiple alternatives), OpenRouteService (driving-hgv), Google Routes, Mapbox Directions | P0 |

### 4.4 Checkpoints and ETA

| ID | Requirement | Pri |
| --- | --- | --- |
| CP-1 | Walk each route geometry with cumulative distance and place a checkpoint every N miles starting at mile 0. Origin and destination are always checkpoints, so a trip shorter than N miles still has two | P0 |
| CP-2 | ETA at a checkpoint is departure time plus cumulative travel time at that distance, interpolated from the provider's per-section durations (not total distance divided by an average speed). If section durations are unavailable, interpolate by distance within the available sections and mark the ETAs as estimates | P0 |
| CP-3 | Weather for a checkpoint comes from the forecast at its ETA, linearly interpolated between the two bracketing hourly values | P0 |
| CP-4 | Segment attribution: each checkpoint owns the stretch from the midpoint to the previous checkpoint to the midpoint to the next, so miles per risk level sum exactly to the route distance | P0 |
| CP-5 | Show ETAs in the local time of each checkpoint, with timezone abbreviation, correct across timezone lines and DST | P0 |
| CP-6 | Driver breaks and hours-of-service delays added to ETA | P2 |

### 4.5 Weather

| ID | Requirement | Pri |
| --- | --- | --- |
| WX-1 | Weather provider adapter. Primary candidate is Open-Meteo (free hourly forecast, imperial units, multi-location requests, no key for development; check commercial-use terms). Optional fallback NWS for US. Variables: wind speed (sustained), gusts, rain, snowfall, temperature, precipitation probability | P0 |
| WX-2 | Request in mph and inches. Batch locations, snap coordinates to the forecast grid (about 0.1 degree) and de-duplicate, fetch in parallel with timeout and retry with backoff | P0 |
| WX-3 | Cache per grid cell and hour, TTL 30 to 60 min. Checkpoint analysis and heatmap share one weather layer so they never disagree | P0 |
| WX-4 | Failure handling: a checkpoint with missing weather is marked 'unknown', borrows the nearest neighbor with a visible flag, and is never silently classified Low. Show a banner on partial data | P0 |
| WX-5 | Show forecast issue time and data source in the UI | P1 |
| WX-6 | Document definitions: wind is sustained 10 m speed (gusts shown separately), rain is rain plus showers in in/hr, snow is snowfall depth in in/hr | P0 |

### 4.6 Risk engine (the core of the 40%)

Single source of truth for classification, implemented as pure functions with no I/O. Levels are scored Low 0, Moderate 1, High 2, Severe 3, No Travel 4.

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind (mph) | under 25 | 25 to under 35 | 35 to under 45 | 45 to under 55 | 55 or more |
| Rain (in/hr) | under 0.10 | 0.10 to 0.25 | over 0.25 to 0.50 | over 0.50 to 1.00 | over 1.00 |
| Snow (in/hr) | under 0.5 | 0.5 to 1.0 | over 1.0 to 2.0 | over 2.0 to 3.0 | over 3.0 |

Boundary convention: the brief's ranges touch or leave gaps (wind 25–34 then 35–44; rain 0.25 appears in two columns). Wind uses lower-inclusive bounds. Rain and snow use upper-inclusive bounds so that 'over 1.00' and 'over 3.0' are exact. This is documented and unit-tested at every boundary.

| ID | Requirement | Pri |
| --- | --- | --- |
| RK-1 | Classify wind, rain, and snow independently. The checkpoint base level is the worst of the three | P0 |
| RK-2 | Apply load rules after the base level; they can only escalate. (a) Wind 55 mph or more is No Travel for any load. (b) Wind from 45 up to under 55 mph (for example 54.9) with load over 30,000 lb is No Travel. (c) Wind from 35 up to under 45 mph (for example 44.9) with load over 40,000 lb is Severe, or higher if the base level is already higher | P0 |
| RK-3 | Each checkpoint returns the level, numeric score, the driving condition, and a reasons list, for example 'Wind 47 mph with 35,000 lb load, over the 30,000 lb limit: No Travel' | P0 |
| RK-4 | Engine is deterministic and fully table-driven tested, including every boundary and every load rule | P0 |
| RK-5 | Thresholds and load limits live in one config module, not scattered constants | P1 |
| RK-6 | Optional gust-aware mode classifies wind as the max of sustained and gust. Default off to match the brief literally | P2 |

Worked examples:

| Wind | Load | Result | Why |
| --- | --- | --- | --- |
| 56 mph | 10,000 lb | No Travel | Rule (a), any load |
| 47 mph | 35,000 lb | No Travel | Rule (b), over 30,000 lb |
| 47 mph | 28,000 lb | Severe | Base level only |
| 38 mph | 45,000 lb | Severe | Rule (c) escalates High to Severe |
| 38 mph | 35,000 lb | High | No escalation |

### 4.7 Route scoring and recommendation

| ID | Requirement | Pri |
| --- | --- | --- |
| SC-1 | Per-route metrics: total miles, duration, miles at each level (Low through No Travel), distance-weighted average risk score (formula below), unknown miles reported separately, max level, worst checkpoint, No Travel checkpoint count | P0 |
| SC-2 | Ranking follows the brief's order as a strict lexicographic sort: (1) fewest Severe miles, (2) fewest High miles, (3) lowest average risk, (4) shortest travel time. Miles are compared at 0.1 mile precision and average risk at 0.01 to avoid float noise. Routes containing any No Travel miles are marked Blocked and ranked below all unblocked routes | P0 |
| SC-3 | If every route is blocked, show a clear 'No safe route at this departure time' state, still show the least-bad route and why | P0 |
| SC-4 | Plain-language explanation of the pick, for example 'Route B has 0 Severe miles versus 42 on Route A, and costs 38 more minutes than the fastest' | P0 |
| SC-5 | Per-route tradeoff versus the fastest route: time added, Severe and High miles saved. This is how 'balancing weather risk and travel time' is made visible | P0 |
| SC-6 | Departure window finder: re-score the same routes for departures within about plus or minus 12 h in 1 h steps using the already cached 48 h forecast, and suggest a safer departure time. Optional, and the first item to cut if time runs short | P1 |

**Average risk.** A route's average risk is the distance-weighted mean of checkpoint scores (Low 0 to No Travel 4) over the segments each checkpoint owns (CP-4). No Travel miles are included at score 4, so Blocked routes still get a comparable score. Segments with unknown weather are excluded from the average and reported as unknown miles.

```latex
\text{AverageRisk} = \frac{\sum_i \text{Miles}_i \cdot \text{Score}_i}{\sum_i \text{Miles}_i}
```

**Blocked-route cases.**

- One route Blocked, two clear: the clear routes are ranked by the four criteria; the Blocked route is shown last with its reason.
- A Blocked route with fewer Severe miles than a clear route still ranks below it. Any No Travel mile outranks the four criteria.
- All three Blocked: SC-3 applies, and the least-bad route is the one with the fewest No Travel miles, then the four criteria.
- Unknown miles never count as Low. A route with unknown miles carries a data-quality warning.

### 4.8 Map and route display

| ID | Requirement | Pri |
| --- | --- | --- |
| MP-1 | One map showing all 3 routes at once in distinct colors with labels. The selected route is emphasized, the others stay visible and clickable | P0 |
| MP-2 | The selected route line is colored by risk along its length. Other routes use a neutral color | P0 |
| MP-3 | Checkpoint markers colored by risk level with a distinct shape or icon per level (not color alone). Hover or click opens a popup: mile, place, local ETA, wind, rain, snow, temperature, level, and reasons | P0 |
| MP-4 | Origin and destination markers; fit-to-bounds on results, accounting for the side panel | P0 |
| MP-5 | Route cards: label, distance, duration, arrival time, via roads, stacked bar of miles by risk level, average risk, tradeoff versus fastest, Recommended and Blocked badges. Card hover and click sync with the map | P0 |
| MP-6 | Risk profile strip under the route: distance on x, risk color band, hover crosshair linked to the map | P1 |
| MP-7 | Checkpoint table for the selected route, sortable, with a filter for High and above | P1 |
| MP-8 | Legend for risk colors and shapes; clear units everywhere | P0 |

### 4.9 Weather heatmap

The heatmap answers 'what does the weather look like across my corridor at hour H', independent of where the truck is, while the truck-position marker ties it back to the trip.

| ID | Requirement | Pri |
| --- | --- | --- |
| HM-1 | Corridor is the union of the three routes buffered by about 25 miles each side (configurable) | P0 |
| HM-2 | Sample cells along each route about every 10 miles, de-duplicated on the forecast grid, with a hard cell cap (about 1,500). Lateral offsets (about 12 and 25 miles) that widen the corridor are P1 | P0 |
| HM-3 | Server returns one compact payload: for each cell, an array of 49 hourly risk values (hours 0 to 48) plus optional wind, rain, snow arrays. Gzip enabled. Fetched once, after route results render | P0 |
| HM-4 | Slider from 0 to 48 h in 1 h steps relative to departure, showing the absolute local time. Keyboard accessible, previous/next hour buttons, play/pause with speed control | P0 |
| HM-5 | Scrubbing makes no network requests. Render on the GPU (map-library heatmap layer or deck.gl) and switch hours with a data-driven expression reading the hour from each cell's array. Throttle updates to animation frames. Cross-fading between hours and deck.gl are P1; the P0 bar is smooth scrubbing with no refetch, targeting about 60 fps | P0 |
| HM-6 | Layer selector: Overall risk (default), Wind, Rain, Snow, with a legend showing thresholds | P0 overall, P1 per-variable |
| HM-7 | The overall layer applies the same risk engine and load rules as the checkpoints, so heatmap and checkpoint colors never contradict each other | P0 |
| HM-8 | Truck position marker on the selected route at the slider time, with that point's risk, plus tick marks on the slider for the truck's ETA hours | P1 |
| HM-9 | Heatmap toggle and opacity control; loading skeleton with progress; heatmap loads lazily so route results are never blocked | P1 |
| HM-10 | Wind direction arrows overlay | P2 |

### 4.10 UX states, resilience, demo

| ID | Requirement | Pri |
| --- | --- | --- |
| UX-1 | Staged loading feedback (Locating, Routing, Weather, Scoring) and skeleton UI | P1 |
| UX-2 | Friendly error states with retry: no route, provider rate limit, geocode failure, partial weather | P0 |
| UX-3 | Empty state with sample trips | P1 |
| UX-4 | Responsive layout: side panel with map on desktop, bottom sheet on mobile | P1 |
| UX-5 | Accessibility: WCAG AA contrast, colorblind-safe palette plus shapes, ARIA on slider and cards, visible focus | P1 |
| UX-6 | Demo scenario mode (for example `?demo=storm`) that injects deterministic synthetic severe weather, so Severe and No Travel behavior, the load rules, and the heatmap are demonstrable and testable even when real weather is calm. Essential for the Loom | P1 |
| UX-7 | Dark mode | P2 |

### 4.11 Error handling and data quality

All rows are P0.

| Situation | Behavior |
| --- | --- |
| Weather provider down or rate-limited | Retry with backoff, serve cache if available, otherwise mark affected checkpoints Unknown and show a banner |
| A checkpoint has no weather | Borrow the nearest neighbor within one interval and flag it as borrowed; otherwise show Unknown with the popup text 'Weather unavailable at this point'. Never classify as Low |
| Forecast does not cover the request | Departure beyond the provider horizon: validation error naming the latest allowed time. ETA beyond the horizon: checkpoint marked Unknown |
| Routing API returns 0 routes | Clear error with suggestions (check the addresses, confirm both are reachable by road) |
| Routing API returns 1 or 2 distinct routes | Show those routes and explain why (RT-2) |
| Routing API outage or rate limit | Try the secondary provider; otherwise friendly error with retry |
| Section durations missing | Distance-based ETA, labeled as an estimate |
| Invalid or oversized request | 400 with field-level errors; request body size limit; coordinate, weight, and date range validation; per-IP throttling |
| Analysis storage | Results are temporary cache entries (about 1 h TTL) used by the heatmap and departure scan; nothing is persisted. An expired id prompts a re-run |
| External API monitoring | Log every provider failure and response time with the request id |

## 5. Technical design

### 5.1 Stack

| Layer | Choice | Reason |
| --- | --- | --- |
| Frontend | React 18, TypeScript (strict), Vite, Tailwind, TanStack Query, Zustand | Fast dev, typed, simple server-state and UI-state split |
| Map | MapLibre GL JS via react-map-gl (or Mapbox GL), optional deck.gl for heatmap | GPU rendering, data-driven styling |
| Backend | Django 5, Django REST Framework, httpx, drf-spectacular | Brief requires Django; OpenAPI docs for free |
| Cache | Redis in production, local memory in development | Weather, geocode, and analysis caching |
| Hosting | Frontend on Vercel or Netlify; backend on Render, Railway, or Fly; HTTPS and CORS locked to the frontend origin | Free tiers; keep the backend warm |
| Tooling | pytest, ruff, mypy, Vitest, Playwright, ESLint, Prettier, GitHub Actions, Docker Compose | Code quality score |

### 5.2 API contract

| Endpoint | Purpose |
| --- | --- |
| GET /api/v1/geocode/?q= | Autocomplete suggestions |
| POST /api/v1/analyze/ | Body: origin, destination, departureTime (ISO 8601 with offset), loadWeightLb, intervalMiles (10, 25, 50), options. Returns analysisId, recommendedRouteId, recommendation (reasons and tradeoffs), warnings, forecastIssuedAt, and routes |
| GET /api/v1/analyze/{id}/heatmap/ | Compact 0–48 h grid for the corridor of that analysis |
| GET /api/v1/analyze/{id}/departure-window/ | P1 departure scan |
| GET /api/v1/health/ | Uptime and warm-up check |

Each route in the response carries: id, label, summary, encoded geometry, distanceMi, durationMin, arrivalTime, rank, blocked, metrics (miles by level, avgRisk, maxLevel, tradeoffs), risk segments for line coloring, and checkpoints (index, mile, lat/lng, place, ETA UTC and local, weather values, level, score, reasons, dataQuality flag).

### 5.3 Backend modules

`geocoding/`, `routing/` (provider adapters plus route de-duplication), `geometry/` (polyline decode, cumulative distance, point-at-distance, perpendicular offsets), `weather/` (adapter, grid snap, cache, interpolation), `risk/` (pure classification and load rules), `scoring/` (route metrics and recommendation), `analysis/` (orchestration), `api/` (serializers, views, throttling). Risk and scoring have no network or Django imports, so they are trivially testable.

### 5.4 Performance design

- Parallelize provider calls; one batched weather fetch covers checkpoints and heatmap through the shared grid cache.
- Return route results first, heatmap second, so time to first useful result stays low.
- The heatmap payload is precomputed server-side and compact (small integers, gzip); the browser never recomputes risk while scrubbing.
- Lazy-load the map library; memoize layers; avoid React re-renders on slider ticks by driving the map layer directly.
- Simplify geometry for display at low zoom.

## 6. Non-functional requirements

| Area | Target |
| --- | --- |
| Analysis latency | p95 under 6 s cold and under 1.5 s warm for a 1,000 mile trip |
| Heatmap interaction | Smooth slider scrubbing (target about 60 fps) with up to about 1,500 cells, no network calls while scrubbing |
| Frontend weight | Initial JS under 300 KB gzipped, map library lazy-loaded |
| Reliability | Timeouts, retries with backoff, graceful partial-data degradation, never a blank screen |
| Security | API keys server-side only, input validation, per-IP throttling, CORS allow-list |
| Observability | Structured logs with request ids, provider latency and error counts |
| Compatibility | Current Chrome, Safari, Firefox, Edge; mobile Safari and Chrome |

## 7. Testing and quality

- **Risk engine:** table-driven tests for every threshold boundary and every load rule, plus conflicting-condition cases (for example high wind with low rain).
- **Geometry and ETA:** checkpoint spacing, origin and destination inclusion, short trips, cumulative-time interpolation, timezone crossings and DST.
- **Recommendation:** ordering by each of the four criteria, ties, Blocked handling, all-blocked case.
- **API:** contract tests with recorded provider responses, partial failure paths.
- **Frontend:** component tests for the form, cards, popup, slider; Playwright end-to-end on the demo scenario.
- **CI:** lint, type-check, tests on every push. Target at least 85% coverage on `risk/`, `scoring/`, `geometry/`.

### 7.1 Acceptance criteria

**Risk engine**

- Wind 55 mph returns No Travel for any load, including 10,000 lb.
- Wind 54.9 mph with 35,001 lb returns No Travel; with 30,000 lb it returns Severe.
- Wind 44.9 mph with 40,001 lb returns Severe; with 40,000 lb it returns High.
- Wind 24.9 is Low, 25.0 and 34.9 are Moderate, 35.0 is High.
- Rain 0.099 is Low; 0.10 and 0.25 are Moderate; 0.26 is High; 1.00 is Severe; 1.01 is No Travel.
- Snow 0.5 and 1.0 are Moderate; 1.01 is High; 3.0 is Severe; 3.01 is No Travel.
- The checkpoint level is the worst of wind, rain, and snow; load rules never lower it.
- Missing weather never becomes Low.

**Checkpoints and ETA**

- Checkpoints sit at mile 0, every N miles, and the destination; a trip shorter than N miles has two.
- Miles by level plus unknown miles equal the route distance within 0.1 mile.
- ETAs never decrease along a route, and the last one equals the route's arrival time.
- With a mock forecast that changes hourly, each checkpoint uses the hour of its own ETA.
- ETAs display in local checkpoint time, including a trip that crosses a timezone line or a DST change.

**Routes and recommendation**

- The app returns up to 3 distinct routes and explains when fewer are available.
- All available routes are compared; the order is Severe miles, High miles, average risk, then duration.
- A clear route always outranks a Blocked one; all-Blocked shows the SC-3 state.
- The recommended route shows a plain-language reason with at least one metric difference.

**Heatmap**

- Each cell carries 49 hourly values; scrubbing triggers zero network requests (checked in Playwright).
- The overall heatmap level at a cell equals the risk engine's result for the same inputs and load.

## 8. Deliverables and documentation

**GitHub repository.** Monorepo with `backend/`, `frontend/`, `docs/`; `.env.example`; Docker Compose; Makefile; CI badge.

**README.** Overview with screenshots, architecture diagram, local setup, environment variables, API docs link, the risk rules table, the assumptions table from Section 10, known limitations, and deployment notes.

**Hosted application.** Public URL, backend health-pinged to avoid cold starts, a sample trip preloaded, demo scenario link in the README.

**Loom walkthrough (5–10 min).**

| Time | Content |
| --- | --- |
| 0:00 to 0:45 | Problem and what the app does |
| 0:45 to 2:30 | Enter a trip, show the 3 routes, checkpoints, ETAs, recommendation and its explanation |
| 2:30 to 4:30 | Risk logic: change load weight and show the 30,000 and 40,000 lb rules firing in the demo scenario |
| 4:30 to 6:00 | Heatmap and 0–48 h slider, truck position marker, layer switching |
| 6:00 to 7:30 | Architecture, provider adapters, caching, performance choices |
| 7:30 to 8:30 | Tests, assumptions, tradeoffs, what I would do next |

## 9. Milestones

| Phase | Scope | Outcome |
| --- | --- | --- |
| 0. Setup | Provider spike (3 distinct truck routes, weight support, section durations, quotas), repos, CI, API keys, skeleton deploy | Hello-world live on both hosts |
| 1. Engine | Geometry, checkpoints, ETA, weather adapter and cache, risk engine, scoring, tests | `/analyze` correct and tested |
| 2. Map UI | Form, route cards, map, markers, popups, recommendation banner | End-to-end trip works |
| 3. Heatmap | Corridor grid, compact payload, slider, GPU layer, truck marker | Smooth 0–48 h scrubbing |
| 4. Polish | Demo scenario, departure window finder, accessibility, responsive, error states | P1 complete |
| 5. Ship | README, final deploy, Loom, buffer | All three deliverables |

## 10. Assumptions and decisions

| Ambiguity in the brief | Decision |
| --- | --- |
| 'Every 10 / 25 / 50 miles' | User-selectable interval, default 25, always including origin and destination. Documented as an interpretation |
| Wind: sustained or gusts | Sustained by default per the brief; gusts displayed; gust-aware mode is optional |
| Boundary values and gaps in the thresholds table | Wind lower-inclusive; rain and snow upper-inclusive; load rules use the same continuous wind bands; unit-tested |
| Snow rate definition | Snowfall depth in inches per hour |
| Load weight meaning | Cargo weight as entered, no hard cap (soft warning above 80,000 lb); rules use strictly greater than. Needs client confirmation |
| Load rules apply to which condition | Wind only, exactly as written |
| 'Balancing risk and travel time' versus a strict preference order | Strict order from the brief, with tradeoffs shown on every card and in the explanation |
| Routes containing No Travel | Treated as Blocked and ranked below every clear route, even one with more Severe miles. Needs client approval |
| Heatmap slider reference | Hour 0 is the departure time, labeled with absolute local time. Needs client confirmation |
| Traffic and breaks | Not modeled; ETA uses provider typical durations |
| Forecast provider limits | Provider swappable via adapter; commercial terms checked before launch |

### 10.1 Questions to confirm with the client

Send these as one short email at the start. Build with the defaults below and do not wait for answers.

| Question | Default used until answered |
| --- | --- |
| Does load weight mean cargo weight or total vehicle weight? | Cargo weight as entered, no hard cap |
| Should any No Travel checkpoint block a route? | Yes: Blocked, ranked below all clear routes |
| Does the heatmap start at departure time or the current time? | Departure time (hour 0) |
| Is the 10 / 25 / 50 mile interval chosen by the user, or fixed tiers? | User-selectable, default 25 |
| Should wind gusts count toward wind risk? | No, sustained wind only |
| Are specific routing or weather providers required? | Any provider with a suitable free tier, behind an adapter |

## 11. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Routing API returns fewer than 3 distinct routes | Via-waypoint variants, secondary provider, de-duplication, honest messaging |
| Provider rate limits or outages | Caching, grid de-duplication, retries, fallback provider, partial-data flags |
| Heatmap janks on long trips | Cell cap, precomputed payload, GPU layer, no refetch on scrub |
| Calm real weather hides the feature | Demo scenario mode |
| Hourly forecast resolution versus 10-mile checkpoints | Grid snapping and interpolation, documented limitation |
| Free-tier cold starts during review | Health ping, loading messaging, README warning |
| Scope creep | P0 first; P1/P2 only after tests pass |

## 12. Definition of done

- Every P0 item passes; every row of Section 2 is demonstrable.
- Risk engine boundary tests and recommendation tests green in CI.
- Heatmap scrubbing stays smooth on a cross-country trip.
- Hosted app, GitHub repo, and Loom link are all in the README.
- A reviewer can open the demo scenario and see Severe and No Travel behavior within 30 seconds.
