"use client";

// The schema-driven connector wizard (doc 4 §6): pick a definition, RJSF
// renders its config_schema into a validated form (the entire reason
// config_schema is JSON Schema), choose method + cadence, then branch:
// pull → done; push → webhook URL; agent → compose file + one-time token.

import Form from "@rjsf/core";
import validator from "@rjsf/validator-ajv8";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import type { AgentRegistration, Connector, ConnectorDefinition } from "@/lib/types";

type Step = "pick" | "configure" | "done";

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
      <pre className="max-h-64 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
        {value}
      </pre>
    </div>
  );
}

export default function ConnectorWizard({
  definitions,
}: {
  definitions: ConnectorDefinition[];
}) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("pick");
  const [definition, setDefinition] = useState<ConnectorDefinition | null>(null);
  const [name, setName] = useState("");
  const [method, setMethod] = useState("pull");
  const [cron, setCron] = useState("* * * * *");
  const [secret, setSecret] = useState("");
  const [metricName, setMetricName] = useState("");
  const [metricKey, setMetricKey] = useState("");
  const [seasonalPeriod, setSeasonalPeriod] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Connector | null>(null);
  const [registration, setRegistration] = useState<AgentRegistration | null>(null);

  const methods = definition
    ? ([
        definition.supports_pull && "pull",
        definition.supports_push && "push",
        definition.supports_agent && "agent",
      ].filter(Boolean) as string[])
    : [];

  const submit = async (config: Record<string, unknown>) => {
    if (!definition) return;
    setError(null);
    try {
      const connector = await api.createConnector({
        connector_definition_key: definition.key,
        name: name || definition.name,
        config,
        ingestion_method: method,
        schedule_cron: method === "pull" ? cron : null,
        secret: secret || null,
      });
      if (metricKey) {
        await api.createMetric(connector.id, {
          name: metricName || metricKey,
          key: metricKey,
          seasonal_period: seasonalPeriod ? parseInt(seasonalPeriod, 10) : null,
        });
      }
      let reg: AgentRegistration | null = null;
      if (method === "agent") {
        reg = await api.registerAgent(connector.id);
      }
      setCreated(connector);
      setRegistration(reg);
      setStep("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (step === "pick") {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        {definitions.map((d) => (
          <button
            key={d.id}
            type="button"
            onClick={() => {
              setDefinition(d);
              setMethod(d.supports_pull ? "pull" : d.supports_push ? "push" : "agent");
              setStep("configure");
            }}
            className="rounded-lg border border-slate-200 bg-white p-5 text-left hover:border-blue-400 hover:shadow-sm"
          >
            <div className="font-medium">{d.name}</div>
            <div className="mt-1 text-xs text-slate-500">{d.description}</div>
            <div className="mt-3 flex gap-2 text-xs">
              {d.supports_pull && <span className="rounded bg-slate-100 px-2 py-0.5">pull</span>}
              {d.supports_push && <span className="rounded bg-slate-100 px-2 py-0.5">push</span>}
              {d.supports_agent && <span className="rounded bg-slate-100 px-2 py-0.5">agent</span>}
            </div>
          </button>
        ))}
      </div>
    );
  }

  if (step === "done" && created) {
    const webhookUrl = created.webhook_token
      ? `${api.baseUrl}/webhooks/${created.webhook_token}`
      : null;
    return (
      <div className="space-y-6">
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          Connector <span className="font-medium">{created.name}</span> created.
        </div>
        {webhookUrl && (
          <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="font-medium">Push setup</h2>
            <p className="text-sm text-slate-500">
              Paste this URL into your source platform (e.g. Braze Currents → Custom HTTP
              Connector). Payload shape:{" "}
              <code className="rounded bg-slate-100 px-1">
                {"{metric_key, points: [{timestamp, value}]}"}
              </code>
            </p>
            <CopyBlock label="Webhook URL" value={webhookUrl} />
          </div>
        )}
        {registration && (
          <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="font-medium">Agent setup</h2>
            <p className="text-sm text-slate-500">
              Shown once — the platform stores only a hash of this token. Save the compose
              file next to the <code className="rounded bg-slate-100 px-1">agent/</code>{" "}
              directory and run it where your source credential lives.
            </p>
            <CopyBlock label="Ingestion token (shown once!)" value={registration.ingestion_token} />
            <CopyBlock label="docker-compose.agent.yml" value={registration.compose_file} />
          </div>
        )}
        <button
          type="button"
          onClick={() => router.push("/connectors")}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Go to connectors
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="mb-4 font-medium">{definition?.name} — connection details</h2>
        <div className="mb-4 grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-slate-600">Connector name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={definition?.name}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            />
          </label>
          <label className="block text-sm">
            <span className="text-slate-600">Ingestion method</span>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            >
              {methods.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          {method === "pull" && (
            <>
              <label className="block text-sm">
                <span className="text-slate-600">Cadence (cron)</span>
                <input
                  value={cron}
                  onChange={(e) => setCron(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono"
                />
              </label>
              <label className="block text-sm">
                <span className="text-slate-600">API secret (optional, stored server-side)</span>
                <input
                  type="password"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                />
              </label>
            </>
          )}
        </div>

        <h3 className="mb-1 mt-6 text-sm font-medium text-slate-600">First metric (optional)</h3>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="block text-sm">
            <span className="text-slate-600">Metric key</span>
            <input
              value={metricKey}
              onChange={(e) => setMetricKey(e.target.value)}
              placeholder="signups_hourly"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono"
            />
          </label>
          <label className="block text-sm">
            <span className="text-slate-600">Display name</span>
            <input
              value={metricName}
              onChange={(e) => setMetricName(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            />
          </label>
          <label className="block text-sm">
            <span className="text-slate-600">Seasonal period m</span>
            <input
              value={seasonalPeriod}
              onChange={(e) => setSeasonalPeriod(e.target.value)}
              placeholder="auto"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            />
          </label>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5 rjsf-container">
        <h2 className="mb-4 font-medium">Source configuration</h2>
        {/* The form below is generated from the connector's config_schema —
            adding a new source type never touches this file (ADR-006). */}
        <Form
          schema={(definition?.config_schema ?? {}) as object}
          validator={validator}
          onSubmit={({ formData }) => void submit(formData as Record<string, unknown>)}
        >
          <button
            type="submit"
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Create connector
          </button>
        </Form>
      </div>
    </div>
  );
}
