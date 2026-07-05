import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

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
      <div>
        <h1 className="text-2xl font-semibold">Connectors</h1>
        <p className="mt-1 text-sm text-slate-500">
          Data sources being polled on a schedule. The seeded demo connector
          points at the local sample endpoint and accumulates a point every
          minute.
        </p>
      </div>

      {withMetrics.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          No connectors yet. Run <code className="rounded bg-slate-100 px-1">make seed</code> to
          create the demo connector.
        </div>
      )}

      <ul className="space-y-4">
        {withMetrics.map(({ connector, metrics }) => (
          <li key={connector.id} className="rounded-lg border border-slate-200 bg-white p-5">
            <div className="flex items-center justify-between">
              <div>
                <Link
                  href={`/connectors/${connector.id}`}
                  className="font-medium hover:text-blue-700"
                >
                  {connector.name} →
                </Link>
                <div className="mt-0.5 text-xs text-slate-500">
                  {connector.ingestion_method}
                  {connector.schedule_cron ? ` · cron ${connector.schedule_cron}` : ""}
                </div>
              </div>
              <span
                className={
                  "rounded-full px-3 py-1 text-xs " +
                  (connector.status === "active"
                    ? "bg-emerald-50 text-emerald-700"
                    : connector.status === "error"
                      ? "bg-red-50 text-red-700"
                      : "bg-slate-100 text-slate-600")
                }
              >
                {connector.status}
              </span>
            </div>
            {metrics.length > 0 && (
              <ul className="mt-4 divide-y divide-slate-100 border-t border-slate-100">
                {metrics.map((m) => (
                  <li key={m.id}>
                    <Link
                      href={`/metrics/${m.id}`}
                      className="flex items-center justify-between py-2.5 text-sm hover:text-blue-700"
                    >
                      <span>
                        {m.name}
                        <span className="ml-2 text-xs text-slate-400">{m.key}</span>
                      </span>
                      <span className="text-xs text-slate-400">
                        {m.seasonal_period ? `m=${m.seasonal_period}` : "no seasonality set"} →
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
