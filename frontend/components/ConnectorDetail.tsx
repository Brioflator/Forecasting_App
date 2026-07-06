"use client";

// Connector management hub (doc 4 §3 connectors/[id]): setup info (webhook URL
// / agent onboarding), pause/resume/delete, metric add + manage, poll history.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash } from "@phosphor-icons/react/dist/ssr";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { AgentOnboarding, PushOnboarding } from "@/components/AgentOnboarding";
import type {
  AgentRegistration,
  Connector,
  ConnectorRunItem,
  Metric,
} from "@/lib/types";

function statusBadge(status: string) {
  if (status === "active") return <Badge variant="success">Active</Badge>;
  if (status === "error") return <Badge variant="destructive">Error</Badge>;
  if (status === "paused") return <Badge variant="outline">Paused</Badge>;
  return <Badge variant="outline">{status}</Badge>;
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
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      toast.error("Action failed", { description: message });
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
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-ink">{connector.name}</h1>
            {statusBadge(connector.status)}
          </div>
          <p className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-ink/60">
            <Badge variant="secondary" className="capitalize">
              {connector.ingestion_method}
            </Badge>
            {connector.schedule_cron && (
              <span className="font-mono text-xs tabular-nums text-ink/50">
                cron {connector.schedule_cron}
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="outline" onClick={() => void togglePause()}>
                {connector.status === "paused" ? "Resume" : "Pause"}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {connector.status === "paused"
                ? "Resumes scheduled data collection"
                : "Stops scheduled data collection until resumed"}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="destructive" onClick={() => void remove()}>
                Delete
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Deletes this connector with all its metrics and collected data
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-paprika/10 px-4 py-3 text-sm text-paprika-ink">
          {error}
        </div>
      )}

      {webhookUrl && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Push setup</CardTitle>
            <CardDescription>
              Your source sends data to this endpoint; nothing runs on your side.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PushOnboarding webhookUrl={webhookUrl} />
          </CardContent>
        </Card>
      )}

      {connector.ingestion_method === "agent" && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle className="text-base">Agent setup</CardTitle>
                <CardDescription className="mt-1.5">
                  A collector you run beside your data; credentials never leave
                  your infrastructure.
                </CardDescription>
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="outline" onClick={() => void registerAgent()}>
                    Register new agent
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  Generates a fresh compose file and one-time token for this connector
                </TooltipContent>
              </Tooltip>
            </div>
          </CardHeader>
          <CardContent>
            {registration ? (
              <AgentOnboarding registration={registration} />
            ) : (
              <p className="text-sm text-ink/60">
                The agent runs on your infrastructure and holds your source
                credentials; only numeric points reach this platform. See{" "}
                <Link href="/agents" className="text-hunter hover:underline">
                  Agents
                </Link>{" "}
                for health.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Metrics</CardTitle>
          <CardDescription>The series this connector collects.</CardDescription>
        </CardHeader>
        <CardContent>
          {metrics.length > 0 ? (
            <table className="mb-4 w-full text-left text-sm">
              <thead className="text-xs text-pine">
                <tr>
                  <th className="py-2 font-medium">Name</th>
                  <th className="py-2 font-medium">Key</th>
                  <th className="py-2 font-medium">Seasonal period</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-sage/15">
                {metrics.map((m) => (
                  <tr key={m.id}>
                    <td className="py-2">
                      <Link href={`/metrics/${m.id}`} className="text-hunter hover:underline">
                        {m.name}
                      </Link>
                    </td>
                    <td className="py-2 font-mono text-xs text-ink/70">{m.key}</td>
                    <td className="py-2 font-mono text-xs tabular-nums text-ink/70">
                      {m.seasonal_period ?? "auto"}
                    </td>
                    <td className="py-2 text-right">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-paprika-ink hover:bg-paprika/10"
                            aria-label={`Delete metric ${m.name}`}
                            onClick={() => void removeMetric(m)}
                          >
                            <Trash size={16} weight="regular" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          Deletes this metric and its collected data
                        </TooltipContent>
                      </Tooltip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="mb-4 text-sm text-ink/50">
              No metrics yet. Add the first one below to start collecting.
            </p>
          )}
          <div className="flex flex-wrap items-end gap-3 border-t border-sage/15 pt-4">
            <div className="space-y-1.5">
              <Label htmlFor="detail-metric-key" className="text-xs">
                Metric key
              </Label>
              <Input
                id="detail-metric-key"
                value={metricKey}
                onChange={(e) => setMetricKey(e.target.value)}
                placeholder="signups_hourly"
                className="h-9 font-mono text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="detail-metric-name" className="text-xs">
                Display name
              </Label>
              <Input
                id="detail-metric-name"
                value={metricName}
                onChange={(e) => setMetricName(e.target.value)}
                className="h-9 text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="detail-metric-seasonal" className="text-xs">
                Seasonal period m
              </Label>
              <Input
                id="detail-metric-seasonal"
                value={seasonal}
                onChange={(e) => setSeasonal(e.target.value)}
                placeholder="auto"
                className="h-9 w-24 font-mono text-sm tabular-nums"
              />
            </div>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  onClick={() => void addMetric()}
                  disabled={!metricKey}
                >
                  <Plus size={16} weight="regular" />
                  Add metric
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                Adds a series this connector will start collecting
              </TooltipContent>
            </Tooltip>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent polls</CardTitle>
          <CardDescription>
            Outcome of the latest scheduled runs for this connector.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {initialRuns.length === 0 ? (
            <p className="py-4 text-center text-sm text-ink/50">
              No poll history yet
              {connector.ingestion_method !== "pull" ? " (not a pull connector)" : ""}.
            </p>
          ) : (
            <ul className="divide-y divide-sage/15">
              {initialRuns.map((r) => (
                <li key={r.id} className="flex items-center gap-3 py-2.5 text-sm">
                  {r.status === "succeeded" ? (
                    <Badge variant="success">Succeeded</Badge>
                  ) : (
                    <Badge variant="destructive">Failed</Badge>
                  )}
                  <span className="font-mono text-xs tabular-nums text-ink/70">
                    {new Date(r.started_at).toLocaleString()}
                  </span>
                  {r.status === "succeeded" ? (
                    <span className="font-mono text-xs tabular-nums text-ink/50">
                      {r.records_ingested ?? 0} point(s)
                    </span>
                  ) : (
                    <span className="text-xs text-paprika-ink">
                      {r.error_message ?? "failed"}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
