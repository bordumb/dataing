/**
 * DataingWidget - Main sidebar widget for Dataing integration.
 *
 * Provides:
 * - Connection status display
 * - Datasource attach UI
 * - SSE streaming for run events
 * - Timeline rendering
 */
import { Widget } from '@lumino/widgets';
import { ISignal } from '@lumino/signaling';
import type { ConnectionState, IDataingState } from './types';
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
    attachedDatasource: string | null;
    currentRunId: string | null;
    timeline: IEvidenceEvent[];
    errorMessage: string | null;
}
/**
 * DataingWidget - Main sidebar widget
 */
export declare class DataingWidget extends Widget {
    private _state;
    private _eventSource;
    private _stateChanged;
    /**
     * Construct a new DataingWidget
     */
    constructor();
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
