// Typed client for the api service — the frontend's only backend (doc 4 §0, §5).

import { authHeaders } from "./auth";
import type {
  AgentInfo,
  AgentRegistration,
  AnomalyItem,
  Connector,
  ConnectorDefinition,
  ConnectorRunItem,
  Dashboard,
  EdaReport,
  ForecastRun,
  ForecastRunSummary,
  Metric,
  MetricData,
  MetricListItem,
  NotificationItem,
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

// For 204-No-Content endpoints: same error contract as req(), no body parse.
// A bare fetch() resolves on 4xx/5xx, which made deletes look successful when
// the backend refused them.
async function reqVoid(path: string, init?: RequestInit): Promise<void> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`api ${res.status} ${path}: ${body}`);
  }
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
  getConnector: (id: string) => req<Connector>(`/connectors/${id}`),
  updateConnector: (id: string, body: Record<string, unknown>) =>
    req<Connector>(`/connectors/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteConnector: (id: string) => reqVoid(`/connectors/${id}`, { method: "DELETE" }),
  listConnectorRuns: (id: string) => req<ConnectorRunItem[]>(`/connectors/${id}/runs`),
  updateMetric: (id: string, body: Record<string, unknown>) =>
    req<Metric>(`/metrics/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteMetric: (id: string) => reqVoid(`/metrics/${id}`, { method: "DELETE" }),
  listMetricForecasts: (id: string) =>
    req<ForecastRunSummary[]>(`/metrics/${id}/forecasts`),
  listMetricAnomalies: (id: string) => req<AnomalyItem[]>(`/metrics/${id}/anomalies`),
  listNotifications: (unreadOnly = false) =>
    req<NotificationItem[]>(`/notifications?unread_only=${unreadOnly}`),
  markNotificationRead: (id: string) =>
    req<NotificationItem>(`/notifications/${id}/read`, { method: "POST" }),
  markAllNotificationsRead: () =>
    req<{ marked_read: number }>("/notifications/read-all", { method: "POST" }),
  getDashboard: () => req<Dashboard>("/dashboard"),
};
