# The frontend

`frontend/` is a Next.js **App Router** app (Next 14, React 18, TypeScript).
It talks **only to the api service** — never to `worker`, `ml`, or the
database — which is what keeps the backend free to change behind the REST
contract.

## Stack

| Concern | Choice | Notes |
|---|---|---|
| Framework | Next.js App Router | Server components for initial loads, `"use client"` leaf components for interactivity/polling |
| Styling | Tailwind CSS + shadcn/ui | Components vendored into `components/ui/`, themed via CSS variables in `app/globals.css` to the botanical palette (design spec: `04-frontend.md` §2b) |
| Charts | Recharts | `ForecastChart` (actuals + dashed forecast + CI band `Area` + zoom/pan/brush via controlled domains, ADR-008) and static `Sparkline` |
| Animation | Motion (`motion/react`) + `components/animate-ui/` primitives | Shared variants in `lib/motion.ts`; see the reduced-motion rule below |
| Icons | @phosphor-icons/react | One family, consistent weight |
| Schema-driven forms | RJSF (`@rjsf/core` + ajv8) | `ConnectorWizard` renders each connector's `config_schema` — adding a connector needs **zero** frontend code |
| Data fetching | Hand-rolled typed client (`lib/api.ts`) + `fetch` | No TanStack Query / global store — deliberate; polling loops are small client effects |
| Toasts | sonner | |

## Layout

```
app/
  layout.tsx                 sidebar shell (AppSidebar), TooltipProvider, fonts
  page.tsx                   dashboard — the bento grid (components/dashboard/*)
  connectors/                list, new/ (wizard), [id]/ (detail: webhook URL,
                             pause/resume, metrics, agent onboarding, run history)
  metrics/                   list; [id]/ is the money screen (MetricDetail:
                             forecast chart, EDA report, history, export/share)
  agents/                    agent health (status, last heartbeat)
  notifications/             notification center
components/
  ui/                        vendored shadcn primitives (themed — never default)
  dashboard/                 bento tiles: FeaturedTile, KpiTile, ForecastPreviewTile,
                             ActivityFeed, CountUp, BotanicalArt, …
  animate-ui/                vendored animate-ui primitives (effects/texts/backgrounds)
  ForecastChart.tsx          pure/presentational; data fetching stays in pages
  ConnectorWizard.tsx        RJSF form from config_schema
  MetricDetail.tsx, ConnectorDetail.tsx, EdaReport.tsx, ExportButtons.tsx,
  AgentOnboarding.tsx, NotificationBell.tsx, Sparkline.tsx
lib/
  api.ts                     the typed client — every endpoint call goes through here
  api-schema.d.ts            generated: npm run gen:api (openapi-typescript)
  types.ts                   hand-curated view types over the schema
  auth.ts                    client-side auth seam (local: fixed session, no token)
  motion.ts                  shared Motion variants + the reduced-motion contract
hooks/                       shared client hooks (e.g. use-is-in-view)
```

## Patterns and invariants

- **All api access goes through `lib/api.ts`.** It picks the right base URL
  per context (server components use `API_URL_INTERNAL` on the docker network;
  the browser uses `NEXT_PUBLIC_API_URL`), attaches auth headers, and throws
  on non-OK — including the `reqVoid` variant for 204 endpoints (a bare
  `fetch()` resolves on 4xx/5xx, which once made failed deletes look
  successful). Add new endpoints here, typed.
- **Polling, not websockets**: forecast completion polls
  `GET /forecasts/{id}` until terminal; the bell polls the cheap
  `unread-count` endpoint. Forecast latency is seconds, so polling is
  imperceptible and much simpler.
- **The reduced-motion SSR trap** (the one frontend rule that will silently
  break accessibility if violated): never strip Motion `variants` for
  `prefers-reduced-motion`. The server renders the hidden styles inline;
  without variants the client never writes the visible state, leaving content
  **permanently invisible** for reduced-motion users. The correct gate is
  `initial={reduceMotion ? false : "hidden"}` while keeping `variants` and
  `animate="visible"`. Full contract in the `lib/motion.ts` JSDoc.
- **Honesty surfaces**: the forecast `warning` and the `low_confidence` verdict
  must be visible on the chart, not buried — this is a product requirement
  (doc 04 §7.0), not styling.
- **Contrast rules** from the botanical palette are binding: sage/fern never
  carry body text; raw paprika never carries or sits under text
  (use `--accent-ink`); ink tokens only. Details: `04-frontend.md` §2b.
- **Type generation**: after any api surface change, run `npm run gen:api`
  against a running api to refresh `lib/api-schema.d.ts`.

## Commands

```bash
cd frontend
npm run dev      # local dev server on :3000
npm run build    # production build (never rebuild .next under a running next start)
npm run lint
npm run gen:api  # regenerate lib/api-schema.d.ts from http://localhost:8000/openapi.json
```

Environment: `NEXT_PUBLIC_API_URL` (browser→api), `API_URL_INTERNAL`
(server-component→api inside compose), `NEXT_PUBLIC_APP_EDITION`
(selects the auth seam; `local` = fixed session, production auth is
deliberately unimplemented until doc 02).
