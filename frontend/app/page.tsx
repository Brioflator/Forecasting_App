// Dashboard (home): the bento-grid overview (doc 4 §7b). Server component:
// all data fetching happens here and is passed down as props; motion lives in
// the "use client" tile components under components/dashboard/.

import { api } from "@/lib/api";
import type {
  Dashboard,
  ForecastRun,
  ForecastRunSummary,
  MetricListItem,
  NotificationItem,
} from "@/lib/types";
import { BentoGrid, BentoTile } from "@/components/dashboard/BentoGrid";
import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import Sparkline from "@/components/Sparkline";
import { FeaturedTile } from "@/components/dashboard/FeaturedTile";
import { KpiTile } from "@/components/dashboard/KpiTile";
import {
  ForecastPreviewTile,
  type ForecastPreviewData,
  type ForecastPreviewRow,
} from "@/components/dashboard/ForecastPreviewTile";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import {
  ChartLineUp,
  Warning,
  Robot,
  Plugs,
  Database,
} from "@phosphor-icons/react/dist/ssr";

export const dynamic = "force-dynamic";

// Composes the forecast-preview tile's data from EXISTING api methods only:
// listAllMetrics() -> listMetricForecasts() per metric to find the most
// recently completed run, then getForecast() for its points and
// getMetricData() for the actuals tail. Works even when no
// forecast_completed notification exists (e.g. all read or pruned).
async function loadForecastPreview(
  metrics: MetricListItem[]
): Promise<ForecastPreviewData | null> {
  if (metrics.length === 0) return null;

  const perMetric = await Promise.all(
    metrics.map(async (m) => {
      try {
        const runs = await api.listMetricForecasts(m.id);
        const completed = runs
          .filter(
            (r): r is ForecastRunSummary & { completed_at: string } =>
              r.status === "completed" && r.completed_at !== null
          )
          .sort(
            (a, b) =>
              new Date(b.completed_at).getTime() - new Date(a.completed_at).getTime()
          );
        return { metric: m, latest: completed[0] ?? null };
      } catch {
        return { metric: m, latest: null };
      }
    })
  );

  const candidates = perMetric.filter(
    (
      p
    ): p is {
      metric: MetricListItem;
      latest: ForecastRunSummary & { completed_at: string };
    } => p.latest !== null
  );
  if (candidates.length === 0) return null;

  candidates.sort(
    (a, b) =>
      new Date(b.latest.completed_at).getTime() - new Date(a.latest.completed_at).getTime()
  );
  const best = candidates[0];

  let forecast: ForecastRun;
  try {
    forecast = await api.getForecast(best.latest.id);
  } catch {
    return null;
  }

  let actualsPoints: { timestamp: string; value: number }[] = [];
  try {
    const data = await api.getMetricData(best.metric.id);
    actualsPoints = data.points;
  } catch {
    // Preview degrades to forecast-only if the actuals fetch fails.
  }

  // Anchor the preview on the forecast window: actuals keep accruing after a
  // run completes, so pairing the forecast with the newest actuals splits the
  // chart into two distant clusters. Show the ~40 actuals leading up to the
  // forecast start, then the forecast continuing from them. Each timestamp is
  // parsed to epoch exactly once here.
  const forecastRows: ForecastPreviewRow[] = forecast.points.map((p) => ({
    t: new Date(p.timestamp).getTime(),
    predicted: p.predicted,
    band: p.lower != null && p.upper != null ? [p.lower, p.upper] : undefined,
  }));
  const forecastStart = forecastRows.length
    ? Math.min(...forecastRows.map((r) => r.t))
    : Number.POSITIVE_INFINITY;

  const actualRows: ForecastPreviewRow[] = actualsPoints.map((p) => ({
    t: new Date(p.timestamp).getTime(),
    actual: p.value,
  }));
  let tail = actualRows.filter((r) => r.t < forecastStart);
  if (tail.length === 0) tail = actualRows;
  tail = tail.slice(-40);

  // Both segments are already chronological and tail precedes the forecast, so
  // the concatenation is sorted without an extra pass.
  const rows = [...tail, ...forecastRows];
  if (rows.length < 2) return null;

  const nowBoundary = tail.length > 0 ? tail[tail.length - 1].t : undefined;

  return {
    metricId: best.metric.id,
    metricName: best.metric.name,
    modelLabel: `${best.latest.resolved_model ?? best.latest.model_type} forecast, next ${best.latest.horizon} points`,
    rows,
    nowBoundary,
  };
}

function ErrorTile({ message }: { message: string }) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-2xl border border-sage/20 bg-surface p-6 text-center shadow-tinted">
      <Warning size={24} weight="regular" className="text-paprika-ink" />
      <p className="text-sm text-ink/60">{message}</p>
    </div>
  );
}

export default async function DashboardPage() {
  let stats: Dashboard | null = null;
  let notifications: NotificationItem[] = [];
  let metrics: MetricListItem[] = [];

  try {
    [stats, notifications, metrics] = await Promise.all([
      api.getDashboard(),
      api.listNotifications(),
      api.listAllMetrics(),
    ]);
  } catch {
    stats = null;
  }

  const header = (
    <DashboardHeader
      title="Overview"
      subtitle="What your data has been doing while you were away."
    />
  );

  if (!stats) {
    return (
      <div className="space-y-8">
        {header}
        <ErrorTile message="Could not load the dashboard right now. Check that the api service is running, then refresh." />
      </div>
    );
  }

  const forecastPreview = await loadForecastPreview(metrics).catch(() => null);
  const featuredSparkline = metrics.find((m) => m.spark && m.spark.length >= 2)?.spark;
  // Wide "Metrics tracked" tile: fill its right edge with the freshest
  // metrics' sparklines instead of leaving the space empty.
  const sparkMetrics = metrics.filter((m) => m.spark && m.spark.length >= 2).slice(0, 3);

  return (
    <div className="space-y-8">
      {header}

      <BentoGrid>
        {/* Featured KPI: 4 cols x 2 rows, pine-teal dark surface */}
        <BentoTile colSpan={4} rowSpan={2} index={0}>
          <FeaturedTile
            dataPoints={stats.data_points}
            pointsLast24h={stats.points_last_24h}
            sparklineValues={featuredSparkline}
          />
        </BentoTile>

        {/* Forecast preview: 5 cols x 2 rows, white */}
        <BentoTile colSpan={5} rowSpan={2} index={1}>
          <ForecastPreviewTile data={forecastPreview} />
        </BentoTile>

        {/* Open anomalies: 3 cols, paprika-tinted when > 0 */}
        <BentoTile colSpan={3} index={2}>
          <KpiTile
            label="Open anomalies"
            value={stats.open_anomalies}
            href="/metrics"
            icon={<Warning size={20} weight="regular" />}
            tone={stats.open_anomalies > 0 ? "paprika" : "plain"}
            subtext={stats.open_anomalies > 0 ? "Needs a look" : "All clear"}
          />
        </BentoTile>

        {/* Active agents: 3 cols, white */}
        <BentoTile colSpan={3} index={3}>
          <KpiTile
            label="Active agents"
            value={stats.agents_active}
            href="/agents"
            icon={<Robot size={20} weight="regular" />}
            subtext="Push agents online"
          />
        </BentoTile>

        {/* Connectors: 3 cols, sage-tinted, error badge when any errored */}
        <BentoTile colSpan={3} index={4}>
          <KpiTile
            label="Connectors"
            value={stats.connectors}
            href="/connectors"
            icon={<Plugs size={20} weight="regular" />}
            tone="sage"
            subtext={
              stats.connectors_error > 0 ? undefined : "All collecting on schedule"
            }
            badge={
              stats.connectors_error > 0 ? `${stats.connectors_error} in error` : undefined
            }
          />
        </BentoTile>

        {/* Forecasts completed: 3 cols, white */}
        <BentoTile colSpan={3} index={5}>
          <KpiTile
            label="Forecasts completed"
            value={stats.forecast_runs_completed}
            href="/metrics"
            icon={<ChartLineUp size={20} weight="regular" />}
            subtext="Across all metrics"
          />
        </BentoTile>

        {/* Recent activity: 6 cols, tall, white */}
        <BentoTile colSpan={6} rowSpan={2} index={6}>
          <ActivityFeed notifications={notifications} />
        </BentoTile>

        {/* Metrics tracked: 6 cols, white — closes the last row against the
            tall activity tile; the wide right edge carries live sparklines
            for the freshest metrics. */}
        <BentoTile colSpan={6} index={7}>
          <KpiTile
            label="Metrics tracked"
            value={stats.metrics}
            href="/metrics"
            icon={<Database size={20} weight="regular" />}
            subtext={sparkMetrics.length > 0 ? "Latest series" : undefined}
            aside={
              sparkMetrics.length > 0 ? (
                <div className="flex flex-col gap-2.5">
                  {sparkMetrics.map((m) => (
                    <div key={m.id} className="flex items-center justify-end gap-3">
                      <span className="max-w-36 truncate text-xs font-medium text-ink/70">
                        {m.name}
                      </span>
                      <Sparkline
                        values={m.spark}
                        width={110}
                        height={22}
                        className="shrink-0 text-hunter/80"
                      />
                    </div>
                  ))}
                </div>
              ) : undefined
            }
          />
        </BentoTile>
      </BentoGrid>
    </div>
  );
}
