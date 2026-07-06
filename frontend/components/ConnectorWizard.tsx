"use client";

// The schema-driven connector wizard (doc 4 §6): pick a definition, RJSF
// renders its config_schema into a validated form (the entire reason
// config_schema is JSON Schema), choose method + cadence, then branch:
// pull -> done; push -> webhook URL; agent -> compose file + one-time token.

import Form from "@rjsf/core";
import validator from "@rjsf/validator-ajv8";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle } from "@phosphor-icons/react/dist/ssr";
import { api } from "@/lib/api";
import { staggerContainer, rise } from "@/lib/motion";
import { cn } from "@/lib/utils";
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
import type { AgentRegistration, Connector, ConnectorDefinition } from "@/lib/types";

type Step = "pick" | "configure" | "done";

const METHOD_INFO: Record<string, { label: string; hint: string; tooltip: string }> = {
  pull: {
    label: "Pull",
    hint: "Scheduled polling",
    tooltip: "The platform calls your source API on the cadence you set below",
  },
  push: {
    label: "Push",
    hint: "Webhook you post to",
    tooltip: "Creates a webhook URL that your source platform posts data points to",
  },
  agent: {
    label: "Agent",
    hint: "Self-hosted collector",
    tooltip: "Generates a compose file and one-time token for a collector you run beside your data",
  },
};

export default function ConnectorWizard({
  definitions,
}: {
  definitions: ConnectorDefinition[];
}) {
  const router = useRouter();
  const reduceMotion = useReducedMotion();
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
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      toast.error("Connector creation failed", { description: message });
    }
  };

  if (step === "pick") {
    return (
      <div className="space-y-4">
        <p className="text-sm font-medium text-pine">
          <span className="font-mono tabular-nums">1.</span> Pick a source type
        </p>
        <motion.div
          initial={reduceMotion ? false : "hidden"}
          animate="visible"
          variants={staggerContainer}
          className="grid gap-4 sm:grid-cols-2"
        >
          {definitions.map((d) => {
            const selected = definition?.id === d.id;
            return (
              <motion.div key={d.id} variants={rise}>
                <button
                  type="button"
                  onClick={() => {
                    setDefinition(d);
                    setMethod(d.supports_pull ? "pull" : d.supports_push ? "push" : "agent");
                    setStep("configure");
                  }}
                  className={cn(
                    "h-full w-full rounded-2xl border bg-surface p-5 text-left shadow-tinted transition-all duration-200",
                    "hover:-translate-y-[2px] hover:shadow-tinted-lg active:scale-[0.98]",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-canvas",
                    selected ? "border-hunter bg-hunter/5" : "border-sage/20"
                  )}
                >
                  <div className="font-medium text-ink">{d.name}</div>
                  <div className="mt-1 text-sm text-ink/60">{d.description}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {d.supports_pull && <Badge variant="secondary">Pull</Badge>}
                    {d.supports_push && <Badge variant="secondary">Push</Badge>}
                    {d.supports_agent && <Badge variant="secondary">Agent</Badge>}
                  </div>
                </button>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    );
  }

  if (step === "done" && created) {
    const webhookUrl = created.webhook_token
      ? `${api.baseUrl}/webhooks/${created.webhook_token}`
      : null;
    return (
      <div className="space-y-6">
        <Card className="border-fern/25">
          <CardContent className="flex items-center gap-3 py-5">
            <CheckCircle size={22} weight="regular" className="shrink-0 text-fern" />
            <p className="text-sm text-ink">
              Connector <span className="font-medium">{created.name}</span> created.
            </p>
          </CardContent>
        </Card>
        {webhookUrl && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Push setup</CardTitle>
              <CardDescription>
                Your source sends data to this endpoint; nothing else to run.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <PushOnboarding webhookUrl={webhookUrl} />
            </CardContent>
          </Card>
        )}
        {registration && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Agent setup</CardTitle>
              <CardDescription>
                Run this pre-filled compose file where your source credential lives.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <AgentOnboarding registration={registration} />
            </CardContent>
          </Card>
        )}
        <Button type="button" onClick={() => router.push("/connectors")}>
          Go to connectors
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-pine">
          <span className="font-mono tabular-nums">2.</span> Configure {definition?.name}
        </p>
        <Button type="button" variant="ghost" size="sm" onClick={() => setStep("pick")}>
          <ArrowLeft size={16} weight="regular" />
          Back to source types
        </Button>
      </div>

      {error && (
        <div className="rounded-lg bg-paprika/10 px-4 py-3 text-sm text-paprika-ink">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Connection details</CardTitle>
          <CardDescription>
            How this connector is named and how its data reaches the platform.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="connector-name">Connector name</Label>
              <Input
                id="connector-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={definition?.name}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Ingestion method</Label>
            <div className="grid gap-3 sm:grid-cols-3">
              {methods.map((m) => {
                const info = METHOD_INFO[m];
                const selected = method === m;
                return (
                  <Tooltip key={m}>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => setMethod(m)}
                        aria-pressed={selected}
                        className={cn(
                          "rounded-lg border p-3 text-left transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          selected
                            ? "border-hunter bg-hunter/5"
                            : "border-sage/40 bg-surface hover:bg-muted/40"
                        )}
                      >
                        <div className="text-sm font-medium text-ink">{info.label}</div>
                        <div className="mt-0.5 text-xs text-ink/60">{info.hint}</div>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>{info.tooltip}</TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </div>

          {method === "pull" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="connector-cron">Cadence (cron)</Label>
                <Input
                  id="connector-cron"
                  value={cron}
                  onChange={(e) => setCron(e.target.value)}
                  className="font-mono tabular-nums"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="connector-secret">API secret (optional, stored server-side)</Label>
                <Input
                  id="connector-secret"
                  type="password"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">First metric (optional)</CardTitle>
          <CardDescription>
            The series this connector will collect. You can add more later from the
            connector detail screen.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="metric-key">Metric key</Label>
              <Input
                id="metric-key"
                value={metricKey}
                onChange={(e) => setMetricKey(e.target.value)}
                placeholder="signups_hourly"
                className="font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="metric-name">Display name</Label>
              <Input
                id="metric-name"
                value={metricName}
                onChange={(e) => setMetricName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="metric-seasonal">Seasonal period m</Label>
              <Input
                id="metric-seasonal"
                value={seasonalPeriod}
                onChange={(e) => setSeasonalPeriod(e.target.value)}
                placeholder="auto"
                className="font-mono tabular-nums"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Source configuration</CardTitle>
          <CardDescription>
            Generated from this connector type&apos;s schema; new source types never
            need new form code.
          </CardDescription>
        </CardHeader>
        <CardContent className="rjsf-container">
          {/* The form below is generated from the connector's config_schema;
              adding a new source type never touches this file (ADR-006). */}
          <Form
            schema={(definition?.config_schema ?? {}) as object}
            validator={validator}
            onSubmit={({ formData }) => void submit(formData as Record<string, unknown>)}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="submit">Create connector</Button>
              </TooltipTrigger>
              <TooltipContent>
                Saves the connector and starts collecting via the chosen method
              </TooltipContent>
            </Tooltip>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
