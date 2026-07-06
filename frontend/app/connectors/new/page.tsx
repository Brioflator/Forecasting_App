import ConnectorWizard from "@/components/ConnectorWizard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function NewConnectorPage() {
  const definitions = await api.listConnectorDefinitions();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">New connector</h1>
        <p className="mt-1 text-sm text-ink/60">
          The configuration form is generated from the connector
          definition&apos;s JSON Schema, so new source types appear here
          automatically.
        </p>
      </div>
      <ConnectorWizard definitions={definitions} />
    </div>
  );
}
