import Link from "next/link";
import { Plugs, Plus, ArrowRight } from "@phosphor-icons/react/dist/ssr";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ConnectorListMotion } from "@/components/ConnectorListMotion";

export const dynamic = "force-dynamic";

function statusBadge(status: string) {
  if (status === "active") {
    return <Badge variant="success">Active</Badge>;
  }
  if (status === "error") {
    return <Badge variant="destructive">Error</Badge>;
  }
  if (status === "paused") {
    return <Badge variant="outline">Paused</Badge>;
  }
  return <Badge variant="outline">{status}</Badge>;
}

export default async function ConnectorsPage() {
  const connectors = await api.listConnectors();
  const withMetrics = await Promise.all(
    connectors.map(async (c) => ({
      connector: c,
      metrics: await api.listMetrics(c.id),
    })),
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Connectors</h1>
          <p className="mt-1 text-sm text-ink/60">
            Data sources being polled on a schedule. The seeded demo connector
            points at the local sample endpoint and accumulates a point every
            minute.
          </p>
        </div>
        <Button asChild>
          <Link href="/connectors/new">
            <Plus size={16} weight="regular" />
            New connector
          </Link>
        </Button>
      </div>

      {withMetrics.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <Plugs size={32} weight="regular" className="text-sage" />
            <div>
              <p className="font-medium text-ink">No connectors yet</p>
              <p className="mt-1 text-sm text-ink/60">
                Set up a source with the schema-driven wizard to start
                collecting data.
              </p>
            </div>
            <Button asChild className="mt-2">
              <Link href="/connectors/new">
                <Plus size={16} weight="regular" />
                New connector
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <ConnectorListMotion>
          {withMetrics.map(({ connector, metrics }) => (
            <Card key={connector.id} className="transition-all duration-200 hover:-translate-y-[2px] hover:shadow-tinted-lg">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="truncate text-base">
                      <Link href={`/connectors/${connector.id}`} className="hover:text-hunter">
                        {connector.name}
                      </Link>
                    </CardTitle>
                    <CardDescription className="mt-1 flex flex-wrap items-center gap-2">
                      <Badge variant="secondary" className="capitalize">
                        {connector.ingestion_method}
                      </Badge>
                      {connector.schedule_cron && (
                        <span className="font-mono text-xs tabular-nums text-ink/50">
                          cron {connector.schedule_cron}
                        </span>
                      )}
                    </CardDescription>
                  </div>
                  {statusBadge(connector.status)}
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                {metrics.length > 0 ? (
                  <ul className="divide-y divide-sage/15 border-t border-sage/15">
                    {metrics.map((m) => (
                      <li key={m.id}>
                        <Link
                          href={`/metrics/${m.id}`}
                          className="flex items-center justify-between py-2.5 text-sm text-ink hover:text-hunter"
                        >
                          <span className="truncate">
                            {m.name}
                            <span className="ml-2 font-mono text-xs text-ink/40">{m.key}</span>
                          </span>
                          <span className="flex shrink-0 items-center gap-1 text-xs text-ink/40">
                            {m.seasonal_period ? `m=${m.seasonal_period}` : "no seasonality set"}
                            <ArrowRight size={12} weight="regular" />
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="border-t border-sage/15 pt-3 text-sm text-ink/50">
                    No metrics yet.{" "}
                    <Link href={`/connectors/${connector.id}`} className="text-hunter hover:underline">
                      Add one from the connector detail screen
                    </Link>
                    .
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </ConnectorListMotion>
      )}
    </div>
  );
}
