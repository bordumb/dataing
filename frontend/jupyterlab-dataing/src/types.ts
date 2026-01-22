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
