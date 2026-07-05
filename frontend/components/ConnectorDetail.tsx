"use client";

// Connector management hub (doc 4 §3 connectors/[id]): setup info (webhook URL
// / agent onboarding), pause/resume/delete, metric add + manage, poll history.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import type {
  AgentRegistration,
  Connector,
  ConnectorRunItem,
  Metric,
} from "@/lib/types";

function CopyBlock({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500">{label}</span>
        <button
          type="button"
          className="rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-50"
          onClick={() => {
            void navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </div>
      <pre className="max-h-64 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">{value}</pre>
    </div>
  );
}

export default function ConnectorDetail({
  initial,
  initialMetrics,
  initialRuns,
}: {
  initial: Connector;
  initialMetrics: Metric[];
  initialRuns: ConnectorRunItem[];
}) {
  const router = useRouter();
  const [connector, setConnector] = useState(initial);
  const [metrics, setMetrics] = useState(initialMetrics);
  const [registration, setRegistration] = useState<AgentRegistration | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metricKey, setMetricKey] = useState("");
  const [metricName, setMetricName] = useState("");
  const [seasonal, setSeasonal] = useState("");

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const togglePause = () =>
    act(async () => {
      const next = connector.status === "paused" ? "active" : "paused";
      setConnector(await api.updateConnector(connector.id, { status: next }));
    });

  const remove = () =>
    act(async () => {
      if (!window.confirm(`Delete "${connector.name}" and ALL its metrics + data? This cannot be undone.`)) return;
      await api.deleteConnector(connector.id);
      router.push("/connectors");
    });

  const addMetric = () =>
    act(async () => {
      if (!metricKey) return;
      const created = await api.createMetric(connector.id, {
        name: metricName || metricKey,
        key: metricKey,
        seasonal_period: seasonal ? parseInt(seasonal, 10) : null,
      });
      setMetrics([...metrics, created]);
      setMetricKey("");
      setMetricName("");
      setSeasonal("");
    });

  const removeMetric = (m: Metric) =>
    act(async () => {
      if (!window.confirm(`Delete metric "${m.name}" and its collected data?`)) return;
      await api.deleteMetric(m.id);
      setMetrics(metrics.filter((x) => x.id !== m.id));
    });

  const registerAgent = () =>
    act(async () => {
      setRegistration(await api.registerAgent(connector.id));
    });

  const webhookUrl = connector.webhook_token
    ? `${api.baseUrl}/webhooks/${connector.webhook_token}`
    : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{connector.name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {connector.ingestion_method}
            {connector.schedule_cron ? ` · cron ${connector.schedule_cron}` : ""} ·{" "}
            <span
              className={
                connector.status === "active"
                  ? "text-emerald-600"
                  : connector.status === "error"
                    ? "text-red-600"
                    : "text-slate-500"
              }
            >
              {connector.status}
            </span>
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => void togglePause()}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            {connector.status === "paused" ? "Resume" : "Pause"}
          </button>
          <button
            onClick={() => void remove()}
            className="rounded-md border border-red-200 bg-white px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
          >
            Delete
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}

      {webhookUrl && (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="font-medium">Push setup</h2>
          <p className="text-sm text-slate-500">
            Point your source (e.g. Braze Currents → Custom HTTP Connector) at this URL. Payload:{" "}
            <code className="rounded bg-slate-100 px-1">{"{metric_key, points: [{timestamp, value}]}"}</code>
          </p>
          <CopyBlock label="Webhook URL" value={webhookUrl} />
        </div>
      )}

      {connector.ingestion_method === "agent" && (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-medium">Agent setup</h2>
            <button
              onClick={() => void registerAgent()}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
            >
              Register new agent
            </button>
          </div>
          {registration ? (
            <>
              <p className="text-sm text-amber-700">
                Save these now — the token is shown exactly once.
              </p>
              <CopyBlock label="Ingestion token" value={registration.ingestion_token} />
              <CopyBlock label="docker-compose.agent.yml" value={registration.compose_file} />
            </>
          ) : (
            <p className="text-sm text-slate-500">
              The agent runs on your infrastructure and holds your source credentials; only
              numeric points reach this platform. See <Link href="/agents" className="text-blue-700 hover:underline">Agents</Link> for health.
            </p>
          )}
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="mb-3 font-medium">Metrics</h2>
        {metrics.length > 0 && (
          <table className="mb-4 w-full text-left text-sm">
            <thead className="text-xs text-slate-500">
              <tr>
                <th className="py-2 font-medium">Name</th>
                <th className="py-2 font-medium">Key</th>
                <th className="py-2 font-medium">Seasonal period</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {metrics.map((m) => (
                <tr key={m.id}>
                  <td className="py-2">
                    <Link href={`/metrics/${m.id}`} className="text-blue-700 hover:underline">
                      {m.name}
                    </Link>
                  </td>
                  <td className="py-2 font-mono text-xs">{m.key}</td>
                  <td className="py-2">{m.seasonal_period ?? "auto"}</td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => void removeMetric(m)}
                      className="text-xs text-red-600 hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="flex flex-wrap items-end gap-3 border-t border-slate-100 pt-4">
          <label className="block text-sm">
            <span className="text-xs text-slate-500">Metric key</span>
            <input
              value={metricKey}
              onChange={(e) => setMetricKey(e.target.value)}
              placeholder="signups_hourly"
              className="mt-1 rounded-md border border-slate-300 px-3 py-1.5 font-mono text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs text-slate-500">Display name</span>
            <input
              value={metricName}
              onChange={(e) => setMetricName(e.target.value)}
              className="mt-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs text-slate-500">Seasonal period m</span>
            <input
              value={seasonal}
              onChange={(e) => setSeasonal(e.target.value)}
              placeholder="auto"
              className="mt-1 w-24 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </label>
          <button
            onClick={() => void addMetric()}
            disabled={!metricKey}
            className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Add metric
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white">
        <h2 className="border-b border-slate-100 px-5 py-3 font-medium">Recent polls</h2>
        {initialRuns.length === 0 ? (
          <div className="p-6 text-center text-sm text-slate-500">
            No poll history yet{connector.ingestion_method !== "pull" ? " (not a pull connector)" : ""}.
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {initialRuns.map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                <span
                  className={
                    "h-2 w-2 shrink-0 rounded-full " +
                    (r.status === "succeeded" ? "bg-emerald-500" : "bg-red-500")
                  }
                />
                <span className="text-slate-600">
                  {new Date(r.started_at).toLocaleString()}
                </span>
                <span className="text-xs text-slate-400">
                  {r.status === "succeeded"
                    ? `${r.records_ingested ?? 0} point(s)`
                    : (r.error_message ?? "failed")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
