import ConnectorDetail from "@/components/ConnectorDetail";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ConnectorPage({ params }: { params: { id: string } }) {
  const [connector, metrics, runs] = await Promise.all([
    api.getConnector(params.id),
    api.listMetrics(params.id),
    api.listConnectorRuns(params.id),
  ]);
  return <ConnectorDetail initial={connector} initialMetrics={metrics} initialRuns={runs} />;
}
