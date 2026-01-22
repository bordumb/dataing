/**
 * DataingWidget - Main sidebar widget for Dataing integration.
 *
 * Provides:
 * - Connection status display
 * - Connection wizard for configuring backend
 * - Datasource attach UI
 * - SSE streaming for run events
 * - Timeline rendering
 */
import { Panel } from '@lumino/widgets';
import { ISignal } from '@lumino/signaling';
import type { ConnectionState, IDataingState } from './types';
import type { CredentialMode } from './components/ConnectionWizard';
/**
 * Evidence event from SSE stream
 */
export interface IEvidenceEvent {
    seq: number;
    event: string;
    run_id: string;
    data: Record<string, unknown>;
    timestamp: string | null;
}
/**
 * Widget state
 */
export interface IDataingWidgetState {
    connectionState: ConnectionState;
    backendUrl: string;
    credentialMode: CredentialMode | null;
    showWizard: boolean;
    attachedDatasource: string | null;
    currentRunId: string | null;
    timeline: IEvidenceEvent[];
    errorMessage: string | null;
    workspaceId: string | null;
    kernelId: string | null;
}
/**
 * DataingWidget - Main sidebar widget
 */
export declare class DataingWidget extends Panel {
    private _state;
    private _eventSource;
    private _stateChanged;
    private _wizardWidget;
    private _contentWidget;
    private _serverBaseUrl;
    _updateBackendUrl?: (url: string) => Promise<void>;
    _getRecentUrls?: () => string[];
    /**
     * Construct a new DataingWidget
     */
    constructor();
    /**
     * Set the server base URL (used for wizard API calls)
     */
    setServerBaseUrl(url: string): void;
    /**
     * Set the workspace ID (generated on first launch, persisted)
     */
    setWorkspaceId(workspaceId: string): void;
    /**
     * Set the active kernel ID (from current notebook)
     * Pass null when no notebook is active or no kernel is running
     */
    setActiveKernel(kernelId: string | null): void;
    /**
     * Get current workspace context (workspace_id + kernel_id)
     */
    getWorkspaceContext(): {
        workspaceId: string | null;
        kernelId: string | null;
    };
    /**
     * Signal emitted when state changes
     */
    get stateChanged(): ISignal<this, IDataingWidgetState>;
    /**
     * Get current state
     */
    get state(): IDataingWidgetState;
    /**
     * Update state from external source
     */
    updateFromState(appState: IDataingState): void;
    /**
     * Show the connection wizard
     */
    showWizard(): void;
    /**
     * Hide the connection wizard
     */
    hideWizard(): void;
    /**
     * Handle wizard connect callback
     */
    private _handleWizardConnect;
    /**
     * Handle wizard cancel callback
     */
    private _handleWizardCancel;
    /**
     * Copy connection snippet to clipboard
     *
     * Fetches the snippet from the server to include attach commands
     * and proper credential mode comments.
     */
    private _copySnippet;
    /**
     * Attach to a datasource
     */
    attach(datasourceId: string, name?: string): void;
    /**
     * Detach from current datasource
     */
    detach(): void;
    /**
     * Start streaming SSE events for a run
     *
     * @param runId - The run ID to stream events for
     * @param serverBaseUrl - Jupyter server base URL (for SSE proxy)
     * @param useProxy - Whether to use the server extension SSE proxy (default: true)
     */
    streamRun(runId: string, serverBaseUrl: string, useProxy?: boolean): void;
    /**
     * Stop SSE streaming
     */
    stopStream(): void;
    /**
     * Format credential mode for display
     */
    private _formatCredentialMode;
    /**
     * Render the widget
     */
    private _render;
    /**
     * Render timeline events
     */
    private _renderTimeline;
    /**
     * Dispose of the widget
     */
    dispose(): void;
}
