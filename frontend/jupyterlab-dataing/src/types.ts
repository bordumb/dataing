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
}
