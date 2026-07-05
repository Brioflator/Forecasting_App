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

### Non-functional
- **Local-first parity:** runs in the compose stack (doc 1) pointed at the local `api`, no cloud account. Same code, prod points at deployed `api` + Supabase Auth.
- **Responsive & accessible:** it's a dashboard; it should work on a laptop and degrade sanely on a tablet.
- **No secrets in the client:** the frontend never sees a source API credential (that's the whole security posture, guide §7) and in production holds only the Supabase anon key, never the service-role key (doc 2 §4.4).

---

## 2. Stack decisions (pinned, with rationale)

| Concern | Choice | Why |
|---|---|---|
| Framework | **Next.js App Router** | Current default; server components fetch from `api` cleanly, client components handle interactivity. Pages Router would be choosing the legacy path on a greenfield build. |
| Language | **TypeScript** | Non-negotiable for a typed contract against the `api`. Generate types from the `api` OpenAPI schema (§5). |
| Styling | **Tailwind CSS + shadcn/ui** | The guide already references shadcn. Tailwind for layout, shadcn for accessible primitives (dialog, form, toast) so you're not hand-rolling a component library. |
| Charts | **Recharts** | Renders the actuals + forecast line + CI band (an `Area` between `lower`/`upper` under a `Line`) cleanly and declaratively; strong enough for MVP without the effort of visx/D3. |
| Schema-driven forms | **react-jsonschema-form (RJSF)** | Renders the connector `config_schema` (doc 1 §4.1) directly into a validated form. This is the entire reason `config_schema` is JSON Schema — closing that loop is the point. |
| Data fetching | **TanStack Query** (client) + server components (initial loads) | Query handles the forecast/agent-health **polling** loops (doc 1 §5.4) with caching and background refetch; server components handle first paint. |
| State | Query cache + React state; **no heavy global store** | The app is mostly server-derived data. Redux/Zustand would be over-engineering at this scope. |

These are defaults chosen to be *decidable and buildable*, not the only valid stack. The two that are almost structural — App Router and RJSF — are called out as ADRs (§8) because overturning them would ripple.

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
    layout.tsx                          — nav shell, org switcher (prod), auth guard
/components
  ForecastChart.tsx                     — Recharts: actuals + forecast + CI band
  EdaReport.tsx                         — renders doc 3 §2 /eda output, plain-language first
  ConnectorWizard.tsx                   — RJSF form from config_schema
  AgentOnboarding.tsx                   — compose file + token, copy buttons
  ExportButtons.tsx                     — format picker + shareable-link display
/lib
  api.ts                                — typed client for the api service (§5)
  auth.ts                               — AuthProvider seam, client side (§4)
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

The single most important visual. Requirements:
- **Three layers:** historical actuals (line), forecast (line, visually distinct — dashed or different color), and the confidence band (shaded `Area` between `lower` and `upper` from doc 3 §2's response).
- **A clear "now" boundary** where actuals end and forecast begins.
- **The `warning` field surfaced** (doc 3 §2) — if the forecast fell back to a naive model on a short series, the user must see that caveat on the chart, not discover it later. This is an honesty requirement, not a nicety.
- **Horizon and model visible**, and ideally a model-comparison affordance later (the guide's "second opinion" idea) — design the component to accept multiple forecast series so that's additive, not a rewrite.

Recharts does all of this with `ComposedChart` (Area + Line together). Keep the component pure/presentational — it takes actuals + forecast(s) + metadata as props and renders; data fetching lives in the page.

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

---

## 9. Trade-offs & what to revisit
- **Recharts over visx/D3:** faster to build, less control. Fine for MVP; if forecast visualizations get ambitious (interactive brushing, dense multi-metric overlays) visx is the upgrade path. The pure presentational `ForecastChart` contains the blast radius.
- **Polling over realtime:** the frontend polls for forecast completion and agent health rather than using websockets/Supabase Realtime. Simpler, and forecast latency is seconds not milliseconds so polling is imperceptible. Supabase Realtime is a clean later upgrade for live dashboards if wanted.
- **Minimal global state:** correct now; if cross-screen shared state grows (unlikely at this scope) revisit with a light store, not before.
- **RJSF theming cost:** the one place effort is front-loaded; accepted as bounded versus per-connector forms.

## 10. What this unblocks
The frontend is no longer "a full workstream with near-zero direction." The stack is pinned, the screens are enumerated, the auth seam mirrors doc 1, the `api` contract is the only backend dependency, and the two structural choices (App Router, RJSF) are recorded with reasoning. The metric-detail screen plus the schema-driven wizard are the two pieces to build first; everything else is plumbing to reach them.
