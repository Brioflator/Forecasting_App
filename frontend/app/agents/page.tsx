import Link from "next/link";
import { Robot, Plus } from "@phosphor-icons/react/dist/ssr";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export const dynamic = "force-dynamic";

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 10) return "just now";
  if (seconds < 60) return `${seconds} seconds ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes === 1 ? "1 minute ago" : `${minutes} minutes ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

function statusBadge(status: string) {
  if (status === "active") return <Badge variant="outline">Active</Badge>;
  if (status === "stale") return <Badge variant="destructive">Stale</Badge>;
  if (status === "unreachable") return <Badge variant="destructive">Unreachable</Badge>;
  if (status === "revoked") return <Badge variant="secondary">Revoked</Badge>;
  return <Badge variant="outline">{status}</Badge>;
}

export default async function AgentsPage() {
  const agents = await api.listAgents();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Agents</h1>
        <p className="mt-1 text-sm text-ink/60">
          Self-hosted pollers holding their own credentials. An agent goes{" "}
          <span className="font-medium text-ink">stale</span> when its heartbeat
          stops.
        </p>
      </div>

      {agents.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <Robot size={32} weight="regular" className="text-sage" />
            <div>
              <p className="font-medium text-ink">No agents registered</p>
              <p className="mt-1 text-sm text-ink/60">
                Use the connector wizard&apos;s agent method to get a pre-filled
                compose file and one-time token.
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
        <Card className="overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/50 text-xs text-pine">
              <tr>
                <th className="px-5 py-3 font-medium">Agent</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Last heartbeat</th>
                <th className="px-5 py-3 font-medium">Registered</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sage/15">
              {agents.map((a) => (
                <tr key={a.id}>
                  <td className="px-5 py-3 font-mono text-xs text-ink/70">{a.id}</td>
                  <td className="px-5 py-3">{statusBadge(a.status)}</td>
                  <td
                    className="px-5 py-3 text-sm text-ink"
                    title={a.last_heartbeat_at ?? undefined}
                  >
                    {timeAgo(a.last_heartbeat_at)}
                  </td>
                  <td className="px-5 py-3 font-mono text-xs tabular-nums text-ink/60">
                    {new Date(a.created_at).toLocaleString()}
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
