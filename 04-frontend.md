# Forecast Platform — Build Guide 4: The Frontend

> **What this document is.** The specification for the Next.js frontend — the connector setup wizard, dataset list, forecast/EDA visualization, and export UI that docs 1–2 refer to as "minimal Next.js" without ever specifying. That one phrase is actually a whole workstream; this document gives it direction at the same depth as the other build docs.
>
> Consistent with `forecast-platform-project-guide.md` ("the guide"), doc 1 (local build), doc 2 (deploy), and doc 3 (ml service). The frontend talks **only to the `api` service** (doc 1 §5.2) — never directly to `worker`, `ml`, or (with one narrow exception, §4) the database.

---

## 0. Design stance

1. **The `api` service is the entire backend.** The frontend is a client of doc 1 §5.2's REST contract and nothing else. This keeps the "loosely coupled" property the guide insists on: the frontend can't reach into `worker` or `ml`, so those stay free to change. The one allowed exception is Supabase Auth in production (§4), and even that is narrow and interface-guarded.
2. **The connector `config_schema` drives the wizard.** The single biggest frontend decision falls out of a decision already made: connector definitions carry a JSON Schema (doc 1 §4.1) precisely so the wizard can *render itself* from it. No hand-coded form per connector. This is why "add a connector = one YAML file" holds all the way to the UI.
3. **Minimal but not throwaway.** The MVP UI is small, but it's the product's whole surface for a non-technical user (the guide's target). It should look intentional and be genuinely usable, not a debug panel. The frontend-design skill's guidance on distinctive, non-templated design applies.

---

## 1. Requirements

### Functional (MVP screens)
- **Auth**: sign in / sign up (production); auto-signed-in as the implicit user (local, doc 1 §6.6).
- **Connector wizard**: pick a connector type, fill a form *generated from its `config_schema`*, choose ingestion method (push / agent / pull) and cadence, save.
- **Agent onboarding**: after registering an agent, show the pre-filled `docker-compose.agent.yml` and the one-time token with copy buttons (guide's agent onboarding UX).
- **Push onboarding**: for push connectors, show the webhook URL + "paste into Braze Currents"-style instructions.
- **Dataset list**: metrics with sparklines and last-updated / agent-health status.
- **Metric detail**: the actuals-plus-forecast chart with confidence bands, the EDA report (with the plain-language readings from doc 3 §2), a "Forecast" button, and export buttons.
- **Export**: trigger CSV/JSON/XLSX; surface the shareable expiring link.
- **Dashboard (home)**: a **bento-grid overview** (§7b) — one featured dark KPI tile, a forecast-preview chart tile, anomaly / agent-health / connector tiles, and a recent-activity feed. Tiles vary in size and background; every tile links to its detail screen.

### Non-functional
- **Local-first parity:** runs in the compose stack (doc 1) pointed at the local `api`, no cloud account. Same code, prod points at deployed `api` + Supabase Auth.
- **Responsive & accessible:** it's a dashboard; it should work on a laptop and degrade sanely on a tablet. All text pairings meet **WCAG AA** against the palette in §2b (the palette's own accessibility matrix drives which combinations are allowed).
- **Interactive charts:** the forecast chart supports **zoom (wheel / pinch), drag-pan, and a brush range selector**, with a one-click reset (§7). Sparklines stay static.
- **Purposeful motion:** entry/hover/state animations via Motion (§7c), every one gated by `prefers-reduced-motion`.
- **Tooltips on actions:** every icon-only or non-obvious action carries a shadcn `Tooltip` (§7c). Destructive or stateful actions explain *what will happen*, not just the button's name.
- **No secrets in the client:** the frontend never sees a source API credential (that's the whole security posture, guide §7) and in production holds only the Supabase anon key, never the service-role key (doc 2 §4.4).

---

## 2. Stack decisions (pinned, with rationale)

| Concern | Choice | Why |
|---|---|---|
| Framework | **Next.js App Router** | Current default; server components fetch from `api` cleanly, client components handle interactivity. Pages Router would be choosing the legacy path on a greenfield build. |
| Language | **TypeScript** | Non-negotiable for a typed contract against the `api`. Generate types from the `api` OpenAPI schema (§5). |
| Styling | **Tailwind CSS + shadcn/ui** (installed, themed) | shadcn is not optional decoration: `Card`, `Tooltip`, `Dialog`, `Tabs`, `Badge`, `Select`, `Skeleton`, `Sonner` (toasts) are the building blocks of every screen. Components are generated into `components/ui/` and re-themed to the botanical palette (§2b) — **never shipped in default state**. |
| Charts | **Recharts** with controlled-domain **zoom/pan + `Brush`** | Renders the actuals + forecast line + CI band (an `Area` between `lower`/`upper` under a `Line`) cleanly and declaratively. Interactivity (§7.1) is a controlled `domain` on the axes — wheel/pinch zoom, drag-pan, brush — which Recharts supports without dropping to visx/D3. |
| Animation | **Motion** (`motion/react`) | Staggered tile entry, count-up KPIs, hover lift, animated chart reveal (§7c). Isolated in `"use client"` leaf components; every effect collapses under `prefers-reduced-motion`. |
| Icons | **@phosphor-icons/react** | One icon family across the app, consistent `weight`/size. No hand-rolled SVG paths, no emoji-as-icon. |
| Schema-driven forms | **react-jsonschema-form (RJSF)** | Renders the connector `config_schema` (doc 1 §4.1) directly into a validated form. This is the entire reason `config_schema` is JSON Schema — closing that loop is the point. |
| Data fetching | **TanStack Query** (client) + server components (initial loads) | Query handles the forecast/agent-health **polling** loops (doc 1 §5.4) with caching and background refetch; server components handle first paint. |
| State | Query cache + React state; **no heavy global store** | The app is mostly server-derived data. Redux/Zustand would be over-engineering at this scope. |

These are defaults chosen to be *decidable and buildable*, not the only valid stack. The two that are almost structural — App Router and RJSF — are called out as ADRs (§8), as are the design system and chart-interactivity choices (ADR-007/008), because overturning them would ripple.

---

## 2b. Visual design system (the botanical theme)

The product look is a calm, botanical green language built from a fixed six-color palette. The palette's WCAG matrix was checked up front, and **the contrast results dictate each color's job** — this is the load-bearing rule of the whole theme.

### Palette and roles

| Token | Hex | Role |
|---|---|---|
| `--canvas` | `#F5F4F0` | App background (dust-grey lightened for contrast headroom). |
| `--surface` | `#FFFFFF` | Cards / tiles. |
| `--muted` | `#DAD7CD` *(dust-grey)* | Muted fills, table stripes, skeleton base, hairline borders (with sage). |
| `--ink` | `#24352B` | Body text (pine-teal deepened; ≥10:1 on canvas). |
| `--ink-soft` | `#344E41` *(pine-teal)* | Headings, secondary text — 6.3:1 on dust-grey, AA. Also the **featured dark tile background**. |
| `--primary` | `#3A5A40` *(hunter-green)* | Primary buttons, active nav, links, actuals line. Foreground on it: `#F5F4F0` (≥5.4:1, AA). |
| `--sage` | `#A3B18A` *(dry-sage)* | Decorative fills, chart series, badge backgrounds (with `--ink` text), borders. |
| `--fern` | `#588157` | Confidence-band fill, icons, positive deltas, large-bold labels only. |
| `--accent` | `#E45918` *(spicy-paprika)* | THE alert color: anomaly markers, warning fills, error badges, forecast line. Fills/graphics only. |
| `--accent-ink` | `≈#A8420C` | Paprika darkened until ≥4.5:1 on `--canvas` — the only paprika allowed as text. Verify the ratio computationally when theming. |

Wire these as CSS variables in `globals.css` mapped onto shadcn's semantic tokens (`--background`, `--foreground`, `--primary`, `--muted`, `--accent`, `--destructive`, ring/border) so every shadcn component inherits the theme for free.

### Hard contrast rules (from the palette's own WCAG matrix)

- **Allowed text pairings:** `--ink`/`--ink-soft` on canvas/surface/muted; `#F5F4F0` or `#DAD7CD` on hunter-green or pine-teal (both AA). Nothing else carries body text.
- **Sage and fern never carry body text.** They pass only the 3:1 graphics threshold on light backgrounds — use them for chart strokes/fills, icons, borders, and bold labels ≥18px.
- **Raw paprika never carries text, and never sits under text.** The matrix shows every pairing on `#E45918` fails AA. Warning/error *text* uses `--accent-ink` on a light paprika tint (e.g. `#E45918` at ~12% opacity over surface); solid paprika appears only as a marker, dot-free status fill, chart stroke, or thin emphasis bar.
- **No pure black, no pure white text.** Ink tokens only.

### Typography, shape, elevation

- **Fonts:** Geist Sans (UI) + Geist Mono (numbers, IDs, timestamps) via `next/font`. All KPI and table numbers get `font-mono tabular-nums`.
- **Radius scale (locked):** cards/tiles `rounded-2xl`, controls `rounded-lg`, badges/pills full. No other radii.
- **Shadows:** tinted to the pine hue (e.g. `shadow-[0_1px_3px_rgba(52,78,65,0.08)]`), never pure-black. Elevation is used sparingly — hairline `--sage`/`--muted` borders do most of the separation.
- **Theme lock:** light theme only, `color-scheme: light`. The pine-teal featured tiles are surfaces *within* the light theme, not a mode flip. (Dark mode is a later, deliberate project — the token layer makes it additive.)

---

## 3. Screen-by-screen structure

```
/app
  /(auth)/sign-in, /sign-up            — production only; local auto-authenticates
  /(app)
    /connectors
      page.tsx                          — list existing connectors + "New connector"
      /new/page.tsx                     — the schema-driven wizard (§6)
      /[id]/page.tsx                    — connector detail, its metrics, agent/webhook setup
    /metrics
      /[id]/page.tsx                    — the money screen: forecast chart + EDA + export
    /agents/page.tsx                    — agent health (last heartbeat, status)
    layout.tsx                          — sidebar nav shell (§7b), TooltipProvider, org badge, auth guard
/components
  /ui                                   — generated shadcn components, themed to §2b
  /dashboard                            — bento tiles: KpiTile, FeaturedTile, ActivityFeed, ForecastPreviewTile
  ForecastChart.tsx                     — Recharts: actuals + forecast + CI band + zoom/pan/brush (§7)
  EdaReport.tsx                         — renders doc 3 §2 /eda output, plain-language first
  ConnectorWizard.tsx                   — RJSF form from config_schema, shadcn-themed widgets
  AgentOnboarding.tsx                   — compose file + token, copy buttons
  ExportButtons.tsx                     — format picker + shareable-link display
/lib
  api.ts                                — typed client for the api service (§5)
  auth.ts                               — AuthProvider seam, client side (§4)
  motion.ts                             — shared Motion variants (stagger, rise, count-up), reduced-motion aware
```

The **metric detail screen is the product**; everything else is plumbing to get a user there. Build it first, stub the rest.

---

## 4. Auth — the one place the frontend touches something other than `api`

Mirrors doc 1's `AuthProvider` seam, on the client:

- **Local:** `auth.ts` returns a fixed session immediately; the sign-in routes are skipped. Zero friction — matches doc 1 §6.6 so an evaluator never hits a login wall.
- **Production:** `auth.ts` uses `supabase-js` for sign-in/sign-up and to obtain the JWT, which is then attached as a bearer token on every `api` call. This is the sole production case of the frontend talking to something other than `api`, and it's confined to `auth.ts`. **Only the anon key ships in the client** (doc 2 §4.4); the service-role key never leaves the backend.
- The `APP_EDITION` equivalent on the frontend (an env var like `NEXT_PUBLIC_APP_EDITION`) selects which `auth.ts` implementation is live — the same seam philosophy as doc 1 §2, applied client-side.

Everything else — connectors, metrics, forecasts, exports — goes through `api` with the bearer token, and RLS on the backend (doc 2 §4.4) does the actual isolation. The frontend never enforces tenancy itself; it just carries the token.

---

## 5. Talking to the `api` service

- **Generate the client types from `api`'s OpenAPI schema.** FastAPI emits OpenAPI for free; a codegen step produces TypeScript types so the `lib/api.ts` client is type-safe against the real contract and drift becomes a compile error. This is worth wiring into the build from day one.
- **The polling loops** (forecast completion and agent health) use TanStack Query with a refetch interval, hitting `GET /forecasts/{id}` (doc 1 §5.4) until `status` is terminal, and the agents endpoint for heartbeat freshness. Query's built-in caching/backoff means this is a few lines, not a hand-rolled loop.
- **Export** is a `GET /forecasts/{id}/export?format=…` that returns the file or a job handle; large exports return async (doc 1 §6) so the UI shows a "preparing…" state then reveals the shareable link.

---

## 6. The schema-driven connector wizard (the interesting part)

This is where a normally-tedious surface becomes almost free, because of an upstream decision.

1. Frontend fetches available connector definitions from `api` (each carries its `config_schema`, doc 1 §4.1).
2. User picks one; **RJSF renders `config_schema` into a validated form** — field labels, types, enums (like the `auth_scheme` dropdown), and `required` all come from the schema. No per-connector form code.
3. User picks ingestion method and cadence; the form posts to `POST /connectors`.
4. Branch on method:
   - **pull** → done; polling starts server-side.
   - **push** → show the generated webhook URL + paste-into-source instructions.
   - **agent** → show the pre-filled `docker-compose.agent.yml` + one-time token (the guide's onboarding smoothness goal).

The payoff: adding a whole new source type to the product — new wizard page included — is *still* just the one YAML file from doc 1 §4.1. The frontend didn't grow. That's the loop closing exactly as designed, and it's the strongest argument for the RJSF choice.

A caveat worth stating: RJSF's default widgets are functional but plain. Expect to supply a small set of custom widgets/theme so the wizard matches the rest of the shadcn-styled app rather than looking like a generated form. That styling effort is the real cost of this approach — accepted because it's bounded and one-time, versus per-connector form code which is unbounded and recurring.

---

## 7. The forecast chart

The single most important visual. The goal: a non-technical user looks at it and *understands* — what happened, what we expect, and how sure we are.

### 7.0 Layers and honesty (unchanged requirements)
- **Three layers:** historical actuals (solid `--primary` line), forecast (dashed `--accent` line, unmistakably different), and the confidence band (a soft `--fern` gradient `Area` between `lower` and `upper` from doc 3 §2's response, fading with distance from the line).
- **A clear "now" boundary** where actuals end and forecast begins: a labeled pine-teal `ReferenceLine` plus a faint background tint over the forecast region, so "this part is a prediction" is legible at a glance.
- **The `warning` field surfaced** (doc 3 §2) — if the forecast fell back to a naive model on a short series, the user must see that caveat on the chart, not discover it later. Render it as an `--accent-ink` alert strip above the plot. This is an honesty requirement, not a nicety.
- **Horizon and model visible** as a plain-language caption ("SARIMA forecast, next 24 points, 95% band"), and the component accepts *multiple* forecast series so model comparison later is additive, not a rewrite.
- **Plain-language band explainer:** a small info affordance (tooltip) that says what the shaded band means in one sentence. The band is the part users misread; one sentence fixes it.

### 7.1 Interactivity: zoom, pan, brush
All implemented as a **controlled axis `domain`** in component state — Recharts re-renders the window; no chart-library change needed.

- **Wheel / pinch zoom** centered on the cursor position.
- **Drag-pan** when zoomed (grab cursor communicates it).
- **`Brush`** strip under the plot for coarse range selection — always shows the full series as context while zoomed.
- **Reset**: double-click and an explicit "Reset zoom" button (tooltip: "Back to full range"), shown only while zoomed.
- **Rich tooltip** (custom, shadcn-styled): timestamp, actual and/or predicted value, band range, and — on forecast points — "expected between X and Y". Numbers in mono.
- Zoom state is ephemeral UI state; it never triggers refetching.

Keep the component pure/presentational — it takes actuals + forecast(s) + metadata as props and renders; data fetching lives in the page. Sparklines (`Sparkline.tsx`) stay static and dumb.

---

## 7b. The dashboard bento grid

The home screen is a **bento grid**: a 12-column CSS Grid with mixed tile sizes and deliberate background variety — not a uniform card wall. Exactly as many tiles as there is real content; no filler cells.

**Composition (desktop `lg`, collapses to single column below `md`):**

| Tile | Size | Surface | Content |
|---|---|---|---|
| Featured KPI | 4 cols × 2 rows | **pine-teal dark** (`--ink-soft`, light text) | Data points collected (count-up number, mono), points last 24h as delta, tiny sparkline |
| Forecast preview | 5 cols × 2 rows | white | Mini (non-zooming) forecast chart of the most recently forecast metric, links to its detail screen |
| Open anomalies | 3 cols | white, paprika-tinted when > 0 | Count + worst severity, links to the metric |
| Active agents | 3 cols | white | Count + stale warning if any heartbeat is old |
| Connectors | 3 cols | **sage-tinted** | Count, error badge when any connector is in `error` |
| Forecasts completed | 3 cols | white | Count + last model used |
| Recent activity | 6 cols (tall) | white | Notification feed (top 6), "view all" link |
| Metrics tracked | 6 cols | white | Count, links to dataset list (wide so the grid closes with no empty cell) |

Rules, inherited from the taste-skill and binding here:
- **Background diversity:** at least the featured dark tile and one sage-tinted tile break the white-on-white monotony.
- **Exact cell count** — the grid is reshaped, never padded with an empty tile.
- **Numbers breathe:** big mono numerals, small quiet labels; no borders-inside-borders.
- Every tile is a link (or contains one); hover states (lift + shadow deepen) communicate it.

**Navigation shell:** a light left **sidebar** (Dashboard, Connectors, Datasets, Agents, Notifications) with Phosphor icons and an active-item pill in hunter-green tint; top bar carries the page title, org badge, and notification bell. On mobile the sidebar becomes a sheet/drawer. Nav labels get no tooltips (they have visible labels); the bell and any icon-only controls do.

---

## 7c. Motion & tooltips

**Motion (library: `motion/react`), all gated by `useReducedMotion`:**
- **Dashboard entry:** tiles stagger-rise (~60ms apart, spring, once).
- **KPI count-up** on first view of a numeric tile.
- **Chart draw-in:** actuals line animates once on data load; forecast line + band fade in when a run completes — the *reveal is the payoff* of the forecast button.
- **Hover physics:** tiles and buttons get `-translate-y-[2px]` + tinted-shadow deepen; `:active` presses down (`scale-[0.98]`).
- **Status transitions:** forecast pending → running → completed animates the status badge (layout animation), not just swaps text.
- **Bans carried over:** no infinite loops on informational content, no scroll-hijack, no `window.addEventListener("scroll")`, no motion without a one-sentence purpose.

**Tooltips (shadcn `Tooltip`, `TooltipProvider` once in the layout, ~300ms delay):**
- Every icon-only button (bell, copy buttons, export formats, reset zoom, refresh).
- Every consequential action states the outcome: Forecast button → "Runs a new forecast with the selected model and horizon"; export → "Downloads CSV and creates a share link"; wizard method picker → one-line explanation of push vs agent vs pull.
- Truncated text (metric keys, connector names) gets a tooltip with the full value.
- Tooltips are supplements: no interaction is *only* discoverable via tooltip, and they never hold essential-first-time information.

---

## 8. Architecture Decision Records

### ADR-005: Next.js App Router (not Pages Router)

**Status:** Accepted · **Date:** 2026-07 · **Deciders:** maintainer

**Context.** Greenfield Next.js app; App Router and Pages Router are both available, with different data-fetching models.

**Decision.** App Router, server components for initial data, client components for interactivity/polling.

**Options.** *Pages Router* (rejected: choosing the legacy model on a new build; the ecosystem and Next's own investment have moved to App Router). *App Router* (chosen: current default, cleaner server/client split, better aligned with fetching from an external `api`).

**Consequences.** *Easier:* server-side data loads, streaming, modern patterns. *Harder:* App Router's server/client boundary has a learning curve; some libraries need `"use client"` care (Recharts, RJSF, TanStack Query are all client components). *Revisit:* unlikely; this is the long-term-supported path.

### ADR-006: JSON-Schema-driven forms via RJSF

**Status:** Accepted · **Date:** 2026-07 · **Deciders:** maintainer

**Context.** Each connector's config UI could be hand-coded per type, or generated from the `config_schema` that connector definitions already carry (doc 1 §4.1).

**Decision.** Generate the wizard form from `config_schema` using react-jsonschema-form.

**Options.** *Hand-coded forms per connector* (rejected: unbounded recurring work, defeats the "connector = one YAML file" property). *RJSF* (chosen: renders + validates from the schema; new connectors need no frontend code). 

**Consequences.** *Easier:* adding connectors never touches the frontend; validation is shared with the backend via one schema. *Harder:* RJSF's default look needs custom widgets/theming to match shadcn (§6) — a bounded one-time cost. *Revisit if:* the config UIs become so bespoke that schema-driven rendering fights the design more than per-form code would — not expected for the connector shapes in scope.

### ADR-007: shadcn/ui + fixed botanical palette as the design system

**Status:** Accepted · **Date:** 2026-07 · **Deciders:** maintainer

**Context.** The MVP shipped with hand-rolled Tailwind (blue/slate utility look). The product needs an intentional identity: a user-supplied six-color botanical palette with a known (mostly failing) WCAG matrix, bento dashboard, animations, and tooltips everywhere.

**Decision.** Adopt shadcn/ui (components vendored into `components/ui/`, themed via CSS variables to §2b), with color roles assigned strictly by the palette's contrast matrix: pine/hunter for text and primary surfaces, sage/fern for graphics, paprika for alert fills with a darkened `--accent-ink` for alert text.

**Options.** *Keep hand-rolled Tailwind* (rejected: every dialog/tooltip/toast is bespoke a11y work). *Radix Themes / Material* (rejected: heavier theming fight to reach a custom palette; shadcn's vendored-source model makes the botanical theme a token file, not a fork). *shadcn/ui* (chosen).

**Consequences.** *Easier:* accessible primitives for free (tooltips, dialogs, toasts are load-bearing in this design); theme is one token layer. *Harder:* generated components live in the repo and are ours to maintain; the contrast rules must be enforced in review since the palette makes it easy to ship AA failures. *Revisit if:* dark mode becomes a requirement — the token layer was designed to make that additive.

### ADR-008: Chart interactivity via Recharts controlled domain (not visx/D3)

**Status:** Accepted · **Date:** 2026-07 · **Deciders:** maintainer

**Context.** The dashboard needs zoomable, pannable, brush-selectable forecast charts. Recharts (already in use) has no first-class wheel-zoom, but supports controlled axis domains and a `Brush` component.

**Decision.** Implement zoom/pan/brush as controlled `domain` state on the existing Recharts `ComposedChart` (wheel/pinch handlers set the window; `Brush` gives coarse selection; double-click resets). Stay on Recharts.

**Options.** *visx/D3* (rejected for now: full rewrite of the working chart for interactivity we can get with ~100 lines of domain state; remains the upgrade path). *Recharts controlled domain* (chosen: additive to the existing pure component). *A wrapper lib (e.g. recharts-to-visx bridges)* (rejected: dependency risk for a bounded feature).

**Consequences.** *Easier:* ships now, chart stays pure/presentational (zoom state is local UI state). *Harder:* very dense series (>10k points) will strain SVG rendering — downsample before render if that day comes. *Revisit if:* brushing across multiple linked charts or canvas-level performance is needed — that's the visx trigger from §9.

---

## 9. Trade-offs & what to revisit
- **Recharts over visx/D3:** faster to build, less control. Zoom/pan/brush now live on Recharts via controlled domains (ADR-008); if forecast visualizations get more ambitious (linked brushing across charts, dense multi-metric overlays, canvas rendering) visx is the upgrade path. The pure presentational `ForecastChart` contains the blast radius.
- **Light theme lock:** one theme, no mode flip. The §2b token layer makes dark mode additive later; shipping both now would double the WCAG surface for no MVP value.
- **Motion budget:** animations are entry/feedback only. If the page ever feels busy, the first thing to cut is the count-up, not the chart reveal (the reveal carries meaning; the count-up is garnish).
- **Polling over realtime:** the frontend polls for forecast completion and agent health rather than using websockets/Supabase Realtime. Simpler, and forecast latency is seconds not milliseconds so polling is imperceptible. Supabase Realtime is a clean later upgrade for live dashboards if wanted.
- **Minimal global state:** correct now; if cross-screen shared state grows (unlikely at this scope) revisit with a light store, not before.
- **RJSF theming cost:** the one place effort is front-loaded; accepted as bounded versus per-connector forms.

## 10. What this unblocks
The frontend is no longer "a full workstream with near-zero direction." The stack is pinned, the screens are enumerated, the auth seam mirrors doc 1, the `api` contract is the only backend dependency, and the two structural choices (App Router, RJSF) are recorded with reasoning. The metric-detail screen plus the schema-driven wizard are the two pieces to build first; everything else is plumbing to reach them.
