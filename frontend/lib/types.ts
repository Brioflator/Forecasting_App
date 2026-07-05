// Hand-maintained mirror of the api contract (doc 1 §5.2). The intended path is
// codegen from the api's OpenAPI schema (`npm run gen:api` → openapi-typescript,
// doc 4 §5); these types keep the client usable before that step runs and
// document the shapes the screens depend on.

export interface ConnectorDefinition {
  id: string;
  key: string;
  name: string;
  description: string | null;
  config_schema: Record<string, unknown>;
  supports_push: boolean;
  supports_pull: boolean;
  supports_agent: boolean;
}

export interface Connector {
  id: string;
  connector_definition_id: string;
  name: string;
  config: Record<string, unknown>;
  ingestion_method: string;
  schedule_cron: string | null;
  webhook_token: string | null;
  status: string;
}

export interface Metric {
  id: string;
  connector_id: string;
  name: string;
  key: string;
  unit: string | null;
  seasonal_period: number | null;
}

export interface DataPoint {
  timestamp: string;
  value: number;
  source: string;
}

export interface MetricData {
  metric_id: string;
  points: DataPoint[];
}

export interface ForecastPoint {
  timestamp: string;
  predicted: number;
  lower: number | null;
  upper: number | null;
}

export interface MetricListItem extends Metric {
  connector_name: string;
  n_points: number;
  last_updated: string | null;
  spark: number[];
}

export interface EdaReport {
  id: string;
  metric_id: string;
  generated_at: string;
  stationarity: Record<string, unknown> & { plain?: string };
  seasonality: Record<string, unknown> & { plain?: string };
  acf_pacf: { acf: number[]; pacf: number[]; lags: number[] };
}

export interface AgentInfo {
  id: string;
  connector_id: string | null;
  status: string;
  last_heartbeat_at: string | null;
  created_at: string;
}

export interface AgentRegistration {
  agent: AgentInfo;
  ingestion_token: string;
  compose_file: string;
}

export interface ShareLink {
  share_url: string;
  share_token: string;
  format: string;
  expires_at: string;
}

export interface NotificationItem {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface AnomalyItem {
  id: string;
  metric_id: string;
  detected_at: string;
  actual_value: number;
  expected_value: number | null;
  severity: "low" | "medium" | "high";
  method: string;
  acknowledged_at: string | null;
}

export interface ForecastRunSummary {
  id: string;
  metric_id: string;
  model_type: string;
  resolved_model: string | null;
  horizon: number;
  status: string;
  requested_at: string;
  completed_at: string | null;
  warning: string | null;
  error_message: string | null;
}

export interface ConnectorRunItem {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  records_ingested: number | null;
  error_message: string | null;
}

export interface Dashboard {
  connectors: number;
  connectors_error: number;
  metrics: number;
  data_points: number;
  points_last_24h: number;
  forecast_runs_completed: number;
  agents_active: number;
  unread_notifications: number;
  open_anomalies: number;
}

export interface ForecastRun {
  id: string;
  metric_id: string;
  model_type: string;
  model_params: Record<string, unknown>;
  horizon: number;
  status: "pending" | "running" | "completed" | "failed";
  requested_at: string;
  completed_at: string | null;
  error_message: string | null;
  warning: string | null;
  points: ForecastPoint[];
}
