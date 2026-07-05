// Typed client for the api service — the frontend's only backend (doc 4 §0, §5).

import { authHeaders } from "./auth";
import type {
  AgentInfo,
  AgentRegistration,
  Connector,
  ConnectorDefinition,
  EdaReport,
  ForecastRun,
  Metric,
  MetricData,
  MetricListItem,
  ShareLink,
} from "./types";

// In the compose stack, server components reach the api over the docker
// network (API_URL_INTERNAL=http://api:8000) while the browser uses the
// published localhost port. Client bundles only ever see NEXT_PUBLIC_*.
const PUBLIC_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BASE = (
  typeof window === "undefined"
    ? (process.env.API_URL_INTERNAL ?? PUBLIC_BASE)
    : PUBLIC_BASE
).replace(/\/$/, "");

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`api ${res.status} ${path}: ${body}`);
  }
  return (await res.json()) as T;
}

export const api = {
  baseUrl: BASE,
  listConnectorDefinitions: () =>
    req<ConnectorDefinition[]>("/connector-definitions"),
  listConnectors: () => req<Connector[]>("/connectors"),
  listMetrics: (connectorId: string) =>
    req<Metric[]>(`/connectors/${connectorId}/metrics`),
  getMetric: (metricId: string) => req<Metric>(`/metrics/${metricId}`),
  getMetricData: (metricId: string) =>
    req<MetricData>(`/metrics/${metricId}/data`),
  requestForecast: (metricId: string, horizon: number, model = "auto") =>
    req<ForecastRun>(`/metrics/${metricId}/forecast`, {
      method: "POST",
      body: JSON.stringify({ horizon, model }),
    }),
  getForecast: (forecastId: string) =>
    req<ForecastRun>(`/forecasts/${forecastId}`),
  exportUrl: (forecastId: string, format: "csv" | "json" | "xlsx" = "csv") =>
    `${BASE}/forecasts/${forecastId}/export?format=${format}`,
  shareForecast: (forecastId: string, format: string) =>
    req<ShareLink>(`/forecasts/${forecastId}/share?format=${format}`, { method: "POST" }),
  listAllMetrics: () => req<MetricListItem[]>("/metrics"),
  createConnector: (body: {
    connector_definition_key: string;
    name: string;
    config: Record<string, unknown>;
    ingestion_method: string;
    schedule_cron?: string | null;
    secret?: string | null;
  }) => req<Connector>("/connectors", { method: "POST", body: JSON.stringify(body) }),
  createMetric: (
    connectorId: string,
    body: { name: string; key: string; unit?: string | null; seasonal_period?: number | null },
  ) =>
    req<Metric>(`/connectors/${connectorId}/metrics`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  generateEda: (metricId: string) =>
    req<EdaReport>(`/metrics/${metricId}/eda`, { method: "POST" }),
  latestEda: (metricId: string) => req<EdaReport>(`/metrics/${metricId}/eda`),
  listAgents: () => req<AgentInfo[]>("/agents"),
  registerAgent: (connectorId: string) =>
    req<AgentRegistration>("/agents", {
      method: "POST",
      body: JSON.stringify({ connector_id: connectorId }),
    }),
};
