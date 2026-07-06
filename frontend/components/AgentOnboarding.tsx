"use client";

// Onboarding blocks shared by the wizard's done step and the connector
// detail screen (doc 4 §1: agent onboarding + push onboarding). Mono code
// blocks on the muted/dust surface with icon copy buttons; the one-time
// token carries a visible paprika-ink warning.

import { Copy } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { AgentRegistration } from "@/lib/types";

export function CopyBlock({
  label,
  value,
  warning,
}: {
  label: string;
  value: string;
  warning?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-pine">{label}</span>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              aria-label={`Copy ${label}`}
              onClick={() => {
                void navigator.clipboard.writeText(value);
                toast.success("Copied");
              }}
            >
              <Copy size={16} weight="regular" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Copy to clipboard</TooltipContent>
        </Tooltip>
      </div>
      {warning && (
        <p className="text-xs font-medium text-paprika-ink">{warning}</p>
      )}
      <pre className="max-h-64 overflow-auto rounded-lg bg-muted p-3 font-mono text-xs leading-relaxed text-ink">
        {value}
      </pre>
    </div>
  );
}

export function PushOnboarding({ webhookUrl }: { webhookUrl: string }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink/60">
        Paste this URL into your source platform (for example Braze Currents
        with a Custom HTTP Connector). Payload shape:{" "}
        <code className="rounded bg-muted px-1 font-mono text-xs text-ink">
          {"{metric_key, points: [{timestamp, value}]}"}
        </code>
      </p>
      <CopyBlock label="Webhook URL" value={webhookUrl} />
    </div>
  );
}

export function AgentOnboarding({
  registration,
}: {
  registration: AgentRegistration;
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink/60">
        The agent runs on your infrastructure and holds your source
        credentials; only numeric points reach this platform. Save the compose
        file next to the agent directory and run it where your source
        credential lives.
      </p>
      <CopyBlock
        label="Ingestion token"
        value={registration.ingestion_token}
        warning="Shown once, store it safely. The platform keeps only a hash of this token."
      />
      <CopyBlock
        label="docker-compose.agent.yml"
        value={registration.compose_file}
      />
    </div>
  );
}
