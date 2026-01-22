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
import { Widget, Panel } from '@lumino/widgets';
import { Signal } from '@lumino/signaling';
import { createConnectionWizardWidget } from './connectionWizard';
/**
 * DataingWidget - Main sidebar widget
 */
export class DataingWidget extends Panel {
    /**
     * Construct a new DataingWidget
     */
    constructor() {
        super();
        this._eventSource = null;
        this._stateChanged = new Signal(this);
        this._wizardWidget = null;
        this._serverBaseUrl = '';
        this.id = 'dataing-widget';
        this.title.label = 'Dataing';
        this.title.closable = true;
        this.addClass('jp-DataingWidget');
        this._state = {
            connectionState: 'disconnected',
            backendUrl: '',
            credentialMode: null,
            showWizard: false,
            attachedDatasource: null,
            currentRunId: null,
            timeline: [],
            errorMessage: null,
            workspaceId: null,
            kernelId: null
        };
        // Create content widget for main UI
        this._contentWidget = new Widget();
        this._contentWidget.addClass('jp-DataingWidget-main');
        this.addWidget(this._contentWidget);
        this._render();
    }
    /**
     * Set the server base URL (used for wizard API calls)
     */
    setServerBaseUrl(url) {
        this._serverBaseUrl = url;
    }
    /**
     * Set the workspace ID (generated on first launch, persisted)
     */
    setWorkspaceId(workspaceId) {
        this._state.workspaceId = workspaceId;
    }
    /**
     * Set the active kernel ID (from current notebook)
     * Pass null when no notebook is active or no kernel is running
     */
    setActiveKernel(kernelId) {
        const changed = this._state.kernelId !== kernelId;
        this._state.kernelId = kernelId;
        if (changed) {
            this._render();
            this._stateChanged.emit(this._state);
        }
    }
    /**
     * Get current workspace context (workspace_id + kernel_id)
     */
    getWorkspaceContext() {
        return {
            workspaceId: this._state.workspaceId,
            kernelId: this._state.kernelId
        };
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
     * Show the connection wizard
     */
    showWizard() {
        if (this._wizardWidget) {
            return; // Already showing
        }
        this._state.showWizard = true;
        // Hide main content
        this._contentWidget.hide();
        // Create and show wizard
        this._wizardWidget = createConnectionWizardWidget({
            initialUrl: this._state.backendUrl || 'http://localhost:8000',
            recentUrls: this._getRecentUrls?.() || [],
            serverBaseUrl: this._serverBaseUrl,
            onConnect: this._handleWizardConnect.bind(this),
            onCancel: this._handleWizardCancel.bind(this)
        });
        this.addWidget(this._wizardWidget);
        this._stateChanged.emit(this._state);
    }
    /**
     * Hide the connection wizard
     */
    hideWizard() {
        if (!this._wizardWidget) {
            return;
        }
        this._state.showWizard = false;
        // Remove wizard
        this._wizardWidget.dispose();
        this._wizardWidget = null;
        // Show main content
        this._contentWidget.show();
        this._render();
        this._stateChanged.emit(this._state);
    }
    /**
     * Handle wizard connect callback
     */
    _handleWizardConnect(url, mode) {
        this._state.backendUrl = url;
        this._state.credentialMode = mode;
        // Persist URL to settings if function available
        if (this._updateBackendUrl) {
            void this._updateBackendUrl(url);
        }
        this.hideWizard();
    }
    /**
     * Handle wizard cancel callback
     */
    _handleWizardCancel() {
        this.hideWizard();
    }
    /**
     * Copy connection snippet to clipboard
     *
     * Fetches the snippet from the server to include attach commands
     * and proper credential mode comments.
     */
    async _copySnippet() {
        try {
            const response = await fetch(`${this._serverBaseUrl}dataing/snippet`, {
                credentials: 'same-origin'
            });
            if (response.ok) {
                const data = await response.json();
                const snippet = data.snippet;
                await navigator.clipboard.writeText(snippet);
                console.log('Copied to clipboard:', snippet);
            }
            else {
                // Fallback to simple snippet
                const fallback = `%dataing connect --base-url ${this._state.backendUrl}`;
                await navigator.clipboard.writeText(fallback);
                console.log('Copied fallback to clipboard:', fallback);
            }
        }
        catch (error) {
            // Fallback on error
            const fallback = `%dataing connect --base-url ${this._state.backendUrl}`;
            await navigator.clipboard.writeText(fallback);
            console.log('Copied fallback to clipboard:', fallback);
        }
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
     * Format credential mode for display
     */
    _formatCredentialMode(mode) {
        if (!mode)
            return 'Unknown';
        switch (mode) {
            case 'keychain':
                return 'OS Keychain';
            case 'env_var':
                return 'Environment Variable';
            case 'session':
                return 'Session Only';
            default:
                return mode;
        }
    }
    /**
     * Render the widget
     */
    _render() {
        const { connectionState, backendUrl, credentialMode, attachedDatasource, errorMessage, kernelId } = this._state;
        // Status badge color
        const statusColors = {
            connected: '#10b981',
            disconnected: '#6b7280',
            checking: '#f59e0b',
            error: '#ef4444'
        };
        const isConnected = connectionState === 'connected';
        const isDisconnected = connectionState === 'disconnected' || connectionState === 'error';
        const hasKernel = kernelId !== null;
        this._contentWidget.node.innerHTML = `
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

        ${isDisconnected
            ? `
          <div class="jp-DataingWidget-connect-section">
            <p>Not connected to Dataing backend.</p>
            <button class="jp-DataingWidget-connect-btn">Connect</button>
          </div>
        `
            : ''}

        ${isConnected
            ? `
          <div class="jp-DataingWidget-section">
            <label>Backend URL</label>
            <div class="jp-DataingWidget-value">${backendUrl || 'Not configured'}</div>
          </div>

          <div class="jp-DataingWidget-section">
            <label>Credential Storage</label>
            <div class="jp-DataingWidget-value">${this._formatCredentialMode(credentialMode)}</div>
          </div>

          <div class="jp-DataingWidget-actions">
            <button class="jp-DataingWidget-edit-btn">Edit Connection</button>
            <button class="jp-DataingWidget-copy-btn">Copy Snippet</button>
          </div>

          <div class="jp-DataingWidget-section">
            <label>Notebook Kernel</label>
            <div class="jp-DataingWidget-value">
              ${hasKernel ? '<span style="color: #10b981;">Active</span>' : '<span style="color: #6b7280;">Select a notebook to run investigations</span>'}
            </div>
          </div>

          <div class="jp-DataingWidget-section">
            <label>Attached Datasource</label>
            <div class="jp-DataingWidget-value">
              ${attachedDatasource || 'None'}
              ${attachedDatasource ? '<button class="jp-DataingWidget-detach">Detach</button>' : ''}
            </div>
          </div>
        `
            : ''}

        ${connectionState === 'checking'
            ? `
          <div class="jp-DataingWidget-checking">
            <span class="jp-DataingWidget-spinner"></span>
            <span>Checking connection...</span>
          </div>
        `
            : ''}

        ${errorMessage
            ? `
          <div class="jp-DataingWidget-error">
            ${errorMessage}
          </div>
        `
            : ''}

        <div class="jp-DataingWidget-timeline" id="dataing-timeline">
          <!-- Timeline events rendered here -->
        </div>
      </div>
    `;
        // Add event listeners
        const connectBtn = this._contentWidget.node.querySelector('.jp-DataingWidget-connect-btn');
        if (connectBtn) {
            connectBtn.addEventListener('click', () => this.showWizard());
        }
        const editBtn = this._contentWidget.node.querySelector('.jp-DataingWidget-edit-btn');
        if (editBtn) {
            editBtn.addEventListener('click', () => this.showWizard());
        }
        const copyBtn = this._contentWidget.node.querySelector('.jp-DataingWidget-copy-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => this._copySnippet());
        }
        const detachBtn = this._contentWidget.node.querySelector('.jp-DataingWidget-detach');
        if (detachBtn) {
            detachBtn.addEventListener('click', () => this.detach());
        }
    }
    /**
     * Render timeline events
     */
    _renderTimeline() {
        const timelineEl = this._contentWidget.node.querySelector('#dataing-timeline');
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
