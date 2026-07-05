import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const STATUS_STYLE: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700",
  stale: "bg-amber-50 text-amber-700",
  revoked: "bg-slate-100 text-slate-500",
};

export default async function AgentsPage() {
  const agents = await api.listAgents();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Agents</h1>
        <p className="mt-1 text-sm text-slate-500">
          Self-hosted pollers holding their own credentials. An agent goes{" "}
          <span className="font-medium">stale</span> when its heartbeat stops.
        </p>
      </div>

      {agents.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          No agents registered. Use the connector wizard&apos;s “agent” method to get a
          pre-filled compose file + token.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Agent</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Last heartbeat</th>
                <th className="px-4 py-3 font-medium">Registered</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {agents.map((a) => (
                <tr key={a.id}>
                  <td className="px-4 py-3 font-mono text-xs">{a.id}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-3 py-1 text-xs ${STATUS_STYLE[a.status] ?? ""}`}
                    >
                      {a.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {a.last_heartbeat_at
                      ? new Date(a.last_heartbeat_at).toLocaleString()
                      : "never"}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {new Date(a.created_at).toLocaleString()}
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
