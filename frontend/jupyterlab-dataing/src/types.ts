/**
 * Shared types for the Dataing JupyterLab extension.
 */

/**
 * Connection state type
 */
export type ConnectionState = 'connected' | 'disconnected' | 'checking' | 'error';

/**
 * Dataing extension state
 */
export interface IDataingState {
  backendUrl: string;
  connectionState: ConnectionState;
  lastCheck: Date | null;
  errorMessage: string | null;
}

/**
 * Dataing extension settings
 */
export interface IDataingSettings {
  backendUrl: string;
  autoConnect: boolean;
  connectionCheckInterval: number;
  showStatusBar: boolean;
  recentUrls: string[];
  workspaceId: string;
}

/**
 * Workspace state enum (matches backend State enum)
 */
export type WorkspaceStateValue =
  | 'DISCONNECTED'
  | 'CONNECTED'
  | 'BOUND'
  | 'RUNNING'
  | 'ERROR';

/**
 * Connection state within workspace
 */
export interface IConnectionState {
  base_url: string | null;
  connected: boolean;
  credential_mode: string;
  last_error: string | null;
}

/**
 * Binding state within workspace
 */
export interface IBindingState {
  asset_urn: string | null;
  datasource_id: string | null;
  datasource_name: string | null;
}

/**
 * Run state within workspace
 */
export interface IRunState {
  run_id: string | null;
  status: string;
  last_seq: number;
  started_at: string | null;
}

/**
 * Full workspace state from server
 */
export interface IWorkspaceState {
  workspace_id: string;
  kernel_id: string;
  state_version: number;
  state: WorkspaceStateValue;
  connection: IConnectionState;
  binding: IBindingState;
  run: IRunState;
}

/**
 * Investigation list item from API
 */
export interface IInvestigationItem {
  investigation_id: string;
  status: string;
  created_at: string;
  dataset_id: string;
}

/**
 * Snapshot information
 */
export interface ISnapshotItem {
  checkpoint: string;
  captured_at: string;
  storage_path: string;
  size_bytes?: number;
}

/**
 * Hydration state for tracking progress
 */
export type HydrationState =
  | 'idle'
  | 'downloading'
  | 'deserializing'
  | 'injecting'
  | 'complete'
  | 'error';

/**
 * Fix proposal types - matches backend FixType literal
 */
export type FixType =
  | 'sql_ddl'
  | 'sql_dml'
  | 'dbt_patch'
  | 'python_patch'
  | 'manual_instruction';

/**
 * Fix proposal from synthesis agent
 */
export interface IFixProposal {
  fix_type: FixType;
  description: string;
  code: string;
  confidence: number;
  risks: string[];
  rollback: string | null;
  requires_confirmation: boolean;
  estimated_impact: string;
  target_asset: string;
}

/**
 * Fix validation result from backend
 */
export interface IFixValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  estimated_affected_rows: number | null;
  tables_touched: string[];
}

/**
 * Fix execution result from backend
 */
export interface IFixExecutionResult {
  success: boolean;
  error?: string;
  rows_affected?: number;
  execution_time_ms?: number;
}
