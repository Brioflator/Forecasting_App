import Link from "next/link";
import Sparkline from "@/components/Sparkline";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DatasetsPage() {
  const metrics = await api.listAllMetrics();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Datasets</h1>
        <p className="mt-1 text-sm text-slate-500">
          Every metric being collected, with recent shape and freshness.
        </p>
      </div>

      {metrics.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          No metrics yet — create a connector first.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Metric</th>
                <th className="px-4 py-3 font-medium">Connector</th>
                <th className="px-4 py-3 font-medium">Recent</th>
                <th className="px-4 py-3 font-medium">Points</th>
                <th className="px-4 py-3 font-medium">Last updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {metrics.map((m) => (
                <tr key={m.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/metrics/${m.id}`} className="font-medium text-blue-700">
                      {m.name}
                    </Link>
                    <span className="ml-2 text-xs text-slate-400">{m.key}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{m.connector_name}</td>
                  <td className="px-4 py-3">
                    <Sparkline values={m.spark} />
                  </td>
                  <td className="px-4 py-3 text-slate-600">{m.n_points}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {m.last_updated ? new Date(m.last_updated).toLocaleString() : "never"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
