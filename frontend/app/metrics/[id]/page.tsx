import MetricDetail from "@/components/MetricDetail";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function MetricPage({ params }: { params: { id: string } }) {
  const [metric, data] = await Promise.all([
    api.getMetric(params.id),
    api.getMetricData(params.id),
  ]);
  return <MetricDetail metric={metric} initialData={data} />;
}
