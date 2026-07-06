import Link from "next/link";
import { Database } from "@phosphor-icons/react/dist/ssr";
import Sparkline from "@/components/Sparkline";
import { Card } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DatasetsPage() {
  const metrics = await api.listAllMetrics();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-pine">Datasets</h1>
        <p className="mt-1 text-sm text-ink/60">
          Every metric being collected, with recent shape and freshness.
        </p>
      </div>

      {metrics.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-sage/40 bg-surface p-10 text-center">
          <Database size={28} weight="regular" className="mx-auto text-hunter" />
          <p className="mt-3 text-sm text-ink/60">
            No metrics yet.{" "}
            <Link href="/connectors/new" className="font-medium text-hunter hover:underline">
              Create a connector
            </Link>{" "}
            to start collecting data.
          </p>
        </div>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/60 text-xs text-ink/60">
              <tr>
                <th className="px-5 py-3 font-medium">Metric</th>
                <th className="px-5 py-3 font-medium">Connector</th>
                <th className="px-5 py-3 font-medium">Recent</th>
                <th className="px-5 py-3 font-medium">Points</th>
                <th className="px-5 py-3 font-medium">Last updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sage/15">
              {metrics.map((m) => (
                <tr key={m.id} className="transition-colors hover:bg-muted/40">
                  <td className="px-5 py-3">
                    <Link
                      href={`/metrics/${m.id}`}
                      className="font-medium text-hunter hover:underline"
                    >
                      {m.name}
                    </Link>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="ml-2 inline-block max-w-[10rem] truncate align-bottom font-mono text-xs text-ink/40">
                          {m.key}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent className="font-mono">{m.key}</TooltipContent>
                    </Tooltip>
                  </td>
                  <td className="px-5 py-3 text-ink/70">{m.connector_name}</td>
                  <td className="px-5 py-3">
                    <Sparkline values={m.spark} />
                  </td>
                  <td className="px-5 py-3 font-mono text-xs tabular-nums text-ink/70">
                    {m.n_points}
                  </td>
                  <td className="px-5 py-3 font-mono text-xs tabular-nums text-ink/50">
                    {m.last_updated ? new Date(m.last_updated).toLocaleString() : "never"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
