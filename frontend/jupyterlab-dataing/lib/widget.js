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
import { Signal } from '@lumino/signaling';
/**
 * DataingWidget - Main sidebar widget
 */
export class DataingWidget extends Widget {
    /**
     * Construct a new DataingWidget
     */
    constructor() {
        super();
        this._eventSource = null;
        this._stateChanged = new Signal(this);
        this.id = 'dataing-widget';
        this.title.label = 'Dataing';
        this.title.closable = true;
        this.addClass('jp-DataingWidget');
        this._state = {
            connectionState: 'disconnected',
            backendUrl: '',
            attachedDatasource: null,
            currentRunId: null,
            timeline: [],
            errorMessage: null
        };
        this._render();
    }
    /**
     * Signal emitted when state changes
     */
    get stateChanged() {
        return this._stateChanged;
    }
    /**
     * Get current state
     */
    get state() {
        return { ...this._state };
    }
    /**
     * Update state from external source
     */
    updateFromState(appState) {
        this._state.connectionState = appState.connectionState;
        this._state.backendUrl = appState.backendUrl;
        this._state.errorMessage = appState.errorMessage;
        this._render();
        this._stateChanged.emit(this._state);
    }
    /**
     * Attach to a datasource
     */
    attach(datasourceId, name) {
        this._state.attachedDatasource = name || datasourceId;
        this._render();
        this._stateChanged.emit(this._state);
    }
    /**
     * Detach from current datasource
     */
    detach() {
        this._state.attachedDatasource = null;
        this._render();
        this._stateChanged.emit(this._state);
    }
    /**
     * Start streaming SSE events for a run
     *
     * @param runId - The run ID to stream events for
     * @param serverBaseUrl - Jupyter server base URL (for SSE proxy)
     * @param useProxy - Whether to use the server extension SSE proxy (default: true)
     */
    streamRun(runId, serverBaseUrl, useProxy = true) {
        // Close existing stream
        this.stopStream();
        this._state.currentRunId = runId;
        this._state.timeline = [];
        // Build SSE URL - use proxy to avoid CORS issues
        let sseUrl;
        if (useProxy) {
            // Use server extension SSE proxy: /dataing/sse/api/v1/runs/{id}/events
            sseUrl = `${serverBaseUrl}dataing/sse/api/v1/runs/${runId}/events`;
        }
        else {
            // Direct connection (requires CORS to be configured on backend)
            sseUrl = `${this._state.backendUrl}/api/v1/runs/${runId}/events`;
        }
        try {
            this._eventSource = new EventSource(sseUrl);
            this._eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this._state.timeline.push(data);
                    this._renderTimeline();
                    this._stateChanged.emit(this._state);
                }
                catch (e) {
                    console.error('Failed to parse SSE event:', e);
                }
            };
            this._eventSource.onerror = (error) => {
                console.error('SSE error:', error);
                this._state.errorMessage = 'Stream connection error';
                this._render();
            };
            this._eventSource.onopen = () => {
                this._state.errorMessage = null;
                this._render();
            };
        }
        catch (e) {
            this._state.errorMessage = `Failed to start stream: ${e}`;
            this._render();
        }
    }
    /**
     * Stop SSE streaming
     */
    stopStream() {
        if (this._eventSource) {
            this._eventSource.close();
            this._eventSource = null;
        }
        this._state.currentRunId = null;
    }
    /**
     * Render the widget
     */
    _render() {
        const { connectionState, backendUrl, attachedDatasource, errorMessage } = this._state;
        // Status badge color
        const statusColors = {
            connected: '#10b981',
            disconnected: '#6b7280',
            checking: '#f59e0b',
            error: '#ef4444'
        };
        this.node.innerHTML = `
      <div class="jp-DataingWidget-content">
        <div class="jp-DataingWidget-header">
          <h3>Dataing</h3>
          <span
            class="jp-DataingWidget-status"
            style="background: ${statusColors[connectionState]};"
          >
            ${connectionState}
          </span>
        </div>

        <div class="jp-DataingWidget-section">
          <label>Backend URL</label>
          <div class="jp-DataingWidget-value">${backendUrl || 'Not configured'}</div>
        </div>

        <div class="jp-DataingWidget-section">
          <label>Attached Datasource</label>
          <div class="jp-DataingWidget-value">
            ${attachedDatasource || 'None'}
            ${attachedDatasource ? '<button class="jp-DataingWidget-detach">Detach</button>' : ''}
          </div>
        </div>

        ${errorMessage ? `
          <div class="jp-DataingWidget-error">
            ${errorMessage}
          </div>
        ` : ''}

        <div class="jp-DataingWidget-timeline" id="dataing-timeline">
          <!-- Timeline events rendered here -->
        </div>
      </div>
    `;
        // Add event listeners
        const detachBtn = this.node.querySelector('.jp-DataingWidget-detach');
        if (detachBtn) {
            detachBtn.addEventListener('click', () => this.detach());
        }
    }
    /**
     * Render timeline events
     */
    _renderTimeline() {
        const timelineEl = this.node.querySelector('#dataing-timeline');
        if (!timelineEl)
            return;
        const eventColors = {
            run_started: '#3b82f6',
            run_progress: '#8b5cf6',
            run_evidence: '#10b981',
            run_completed: '#10b981',
            run_failed: '#ef4444',
            run_heartbeat: '#6b7280'
        };
        const eventIcons = {
            run_started: '\uD83D\uDE80',
            run_progress: '\u23F3',
            run_evidence: '\uD83D\uDCCB',
            run_completed: '\u2705',
            run_failed: '\u274C',
            run_heartbeat: '\uD83D\uDC93' // heartbeat
        };
        timelineEl.innerHTML = this._state.timeline
            .map((evt) => `
        <div class="jp-DataingWidget-event" style="border-left-color: ${eventColors[evt.event] || '#6b7280'};">
          <span class="jp-DataingWidget-event-icon">${eventIcons[evt.event] || '\u2022'}</span>
          <span class="jp-DataingWidget-event-type">${evt.event}</span>
          <span class="jp-DataingWidget-event-seq">#${evt.seq}</span>
        </div>
      `)
            .join('');
    }
    /**
     * Dispose of the widget
     */
    dispose() {
        this.stopStream();
        super.dispose();
    }
}
//# sourceMappingURL=widget.js.map