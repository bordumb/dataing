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
import { Signal, ISignal } from '@lumino/signaling';
import type {
  ConnectionState,
  IDataingState,
  IInvestigationItem,
  HydrationState
} from './types';
import {
  ConnectionWizardWidget,
  createConnectionWizardWidget
} from './connectionWizard';
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
  investigations: IInvestigationItem[];
  hydrationState: HydrationState;
  hydrationMessage: string | null;
}

/**
 * DataingWidget - Main sidebar widget
 */
export class DataingWidget extends Panel {
  private _state: IDataingWidgetState;
  private _eventSource: EventSource | null = null;
  private _stateChanged = new Signal<this, IDataingWidgetState>(this);
  private _wizardWidget: ConnectionWizardWidget | null = null;
  private _contentWidget: Widget;
  private _serverBaseUrl: string = '';

  // Functions exposed by index.ts for settings persistence
  _updateBackendUrl?: (url: string) => Promise<void>;
  _getRecentUrls?: () => string[];

  // Reference to notebook tracker (set by index.ts)
  _notebookTracker?: {
    currentWidget: { sessionContext: { session: { kernel: { requestExecute: (content: { code: string }) => { done: Promise<void> } } | null } | null } | null } | null
  } | null;

  /**
   * Construct a new DataingWidget
   */
  constructor() {
    super();
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
      kernelId: null,
      investigations: [],
      hydrationState: 'idle',
      hydrationMessage: null
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
  setServerBaseUrl(url: string): void {
    this._serverBaseUrl = url;
  }

  /**
   * Set the workspace ID (generated on first launch, persisted)
   */
  setWorkspaceId(workspaceId: string): void {
    this._state.workspaceId = workspaceId;
  }

  /**
   * Set the active kernel ID (from current notebook)
   * Pass null when no notebook is active or no kernel is running
   */
  setActiveKernel(kernelId: string | null): void {
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
  getWorkspaceContext(): { workspaceId: string | null; kernelId: string | null } {
    return {
      workspaceId: this._state.workspaceId,
      kernelId: this._state.kernelId
    };
  }

  /**
   * Signal emitted when state changes
   */
  get stateChanged(): ISignal<this, IDataingWidgetState> {
    return this._stateChanged;
  }

  /**
   * Get current state
   */
  get state(): IDataingWidgetState {
    return { ...this._state };
  }

  /**
   * Update state from external source
   */
  updateFromState(appState: IDataingState): void {
    this._state.connectionState = appState.connectionState;
    this._state.backendUrl = appState.backendUrl;
    this._state.errorMessage = appState.errorMessage;
    this._render();
    this._stateChanged.emit(this._state);
  }

  /**
   * Show the connection wizard
   */
  showWizard(): void {
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
  hideWizard(): void {
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
  private _handleWizardConnect(url: string, mode: CredentialMode): void {
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
  private _handleWizardCancel(): void {
    this.hideWizard();
  }

  /**
   * Kernel code execution callback (set by index.ts)
   */
  _executeKernelCode?: (code: string) => Promise<void>;

  /**
   * Fetch recent investigations from API
   */
  async fetchInvestigations(): Promise<void> {
    if (this._state.connectionState !== 'connected') {
      return;
    }

    try {
      const response = await fetch(
        `${this._serverBaseUrl}dataing/proxy/api/v1/investigations`,
        { credentials: 'same-origin' }
      );

      if (response.ok) {
        const data = (await response.json()) as IInvestigationItem[];
        this._state.investigations = data.slice(0, 10); // Limit to 10
        this._render();
        this._stateChanged.emit(this._state);
      }
    } catch (error) {
      console.error('Failed to fetch investigations:', error);
    }
  }

  /**
   * Hydrate an investigation into the kernel
   */
  async hydrate(investigationId: string, checkpoint = 'complete'): Promise<void> {
    if (!this._executeKernelCode) {
      this._state.hydrationState = 'error';
      this._state.hydrationMessage = 'Kernel execution not available. Open a notebook first.';
      this._render();
      return;
    }

    if (!this._state.kernelId) {
      this._state.hydrationState = 'error';
      this._state.hydrationMessage = 'No active kernel. Start a kernel in your notebook first.';
      this._render();
      return;
    }

    try {
      this._state.hydrationState = 'downloading';
      this._state.hydrationMessage = 'Loading magic extension...';
      this._render();

      // Execute the hydration code in the kernel
      const code = `
# Hydrate investigation state
try:
    from IPython import get_ipython
    ip = get_ipython()
    if 'dataing.sdk.magic' not in ip.extension_manager.loaded:
        ip.run_line_magic('load_ext', 'dataing.sdk.magic')
    ip.run_line_magic('dataing', 'hydrate ${investigationId} --checkpoint ${checkpoint}')
except Exception as e:
    print(f"Hydration failed: {e}")
`;

      await this._executeKernelCode(code);

      this._state.hydrationState = 'complete';
      this._state.hydrationMessage = `Hydrated investigation ${investigationId.slice(0, 8)}...`;
    } catch (error) {
      this._state.hydrationState = 'error';
      this._state.hydrationMessage = `Hydration failed: ${error}`;
    }

    this._render();
    this._stateChanged.emit(this._state);

    // Reset state after delay
    setTimeout(() => {
      this._state.hydrationState = 'idle';
      this._state.hydrationMessage = null;
      this._render();
    }, 3000);
  }

  /**
   * Copy connection snippet to clipboard
   *
   * Fetches the snippet from the server to include attach commands
   * and proper credential mode comments.
   */
  private async _copySnippet(): Promise<void> {
    try {
      const response = await fetch(`${this._serverBaseUrl}dataing/snippet`, {
        credentials: 'same-origin'
      });

      if (response.ok) {
        const data = await response.json();
        const snippet = data.snippet as string;
        await navigator.clipboard.writeText(snippet);
        console.log('Copied to clipboard:', snippet);
      } else {
        // Fallback to simple snippet
        const fallback = `%dataing connect --base-url ${this._state.backendUrl}`;
        await navigator.clipboard.writeText(fallback);
        console.log('Copied fallback to clipboard:', fallback);
      }
    } catch (error) {
      // Fallback on error
      const fallback = `%dataing connect --base-url ${this._state.backendUrl}`;
      await navigator.clipboard.writeText(fallback);
      console.log('Copied fallback to clipboard:', fallback);
    }
  }

  /**
   * Attach to a datasource
   */
  attach(datasourceId: string, name?: string): void {
    this._state.attachedDatasource = name || datasourceId;
    this._render();
    this._stateChanged.emit(this._state);
  }

  /**
   * Detach from current datasource
   */
  detach(): void {
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
  streamRun(runId: string, serverBaseUrl: string, useProxy = true): void {
    // Close existing stream
    this.stopStream();

    this._state.currentRunId = runId;
    this._state.timeline = [];

    // Build SSE URL - use proxy to avoid CORS issues
    let sseUrl: string;
    if (useProxy) {
      // Use server extension SSE proxy: /dataing/sse/api/v1/runs/{id}/events
      sseUrl = `${serverBaseUrl}dataing/sse/api/v1/runs/${runId}/events`;
    } else {
      // Direct connection (requires CORS to be configured on backend)
      sseUrl = `${this._state.backendUrl}/api/v1/runs/${runId}/events`;
    }

    try {
      this._eventSource = new EventSource(sseUrl);

      this._eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as IEvidenceEvent;
          this._state.timeline.push(data);
          this._renderTimeline();
          this._stateChanged.emit(this._state);
        } catch (e) {
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
    } catch (e) {
      this._state.errorMessage = `Failed to start stream: ${e}`;
      this._render();
    }
  }

  /**
   * Stop SSE streaming
   */
  stopStream(): void {
    if (this._eventSource) {
      this._eventSource.close();
      this._eventSource = null;
    }
    this._state.currentRunId = null;
  }

  /**
   * Format credential mode for display
   */
  private _formatCredentialMode(mode: CredentialMode | null): string {
    if (!mode) return 'Unknown';
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
   * Format relative time
   */
  private _formatRelativeTime(dateStr: string): string {
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

      if (diffHours < 1) {
        const diffMins = Math.floor(diffMs / (1000 * 60));
        return `${diffMins}m ago`;
      } else if (diffHours < 24) {
        return `${diffHours}h ago`;
      } else {
        const diffDays = Math.floor(diffHours / 24);
        return `${diffDays}d ago`;
      }
    } catch {
      return dateStr;
    }
  }

  /**
   * Render the widget
   */
  private _render(): void {
    const {
      connectionState,
      backendUrl,
      credentialMode,
      attachedDatasource,
      errorMessage,
      kernelId,
      investigations,
      hydrationState,
      hydrationMessage
    } = this._state;

    // Status badge color
    const statusColors: Record<ConnectionState, string> = {
      connected: '#10b981',
      disconnected: '#6b7280',
      checking: '#f59e0b',
      error: '#ef4444'
    };

    const isConnected = connectionState === 'connected';
    const isDisconnected =
      connectionState === 'disconnected' || connectionState === 'error';
    const hasKernel = kernelId !== null;

    // Render investigations list
    const investigationsHtml = investigations.length > 0
      ? investigations
          .map(
            (inv) => `
            <div class="jp-DataingWidget-investigation" data-id="${inv.investigation_id}">
              <div class="jp-DataingWidget-inv-info">
                <span class="jp-DataingWidget-inv-id">${inv.investigation_id.slice(0, 8)}...</span>
                <span class="jp-DataingWidget-inv-time">${this._formatRelativeTime(inv.created_at)}</span>
              </div>
              <div class="jp-DataingWidget-inv-meta">
                <span class="jp-DataingWidget-inv-dataset">${inv.dataset_id}</span>
                <span class="jp-DataingWidget-inv-status jp-DataingWidget-inv-status--${inv.status}">${inv.status}</span>
              </div>
              <button
                class="jp-DataingWidget-hydrate-btn"
                data-investigation-id="${inv.investigation_id}"
                ${!hasKernel ? 'disabled title="Start a kernel to enable hydration"' : ''}
              >
                Hydrate
              </button>
            </div>
          `
          )
          .join('')
      : '<div class="jp-DataingWidget-no-investigations">No recent investigations</div>';

    // Hydration status indicator
    const hydrationIndicator =
      hydrationState !== 'idle'
        ? `
          <div class="jp-DataingWidget-hydration-status jp-DataingWidget-hydration-status--${hydrationState}">
            ${hydrationState === 'downloading' || hydrationState === 'deserializing' || hydrationState === 'injecting' ? '<span class="jp-DataingWidget-spinner"></span>' : ''}
            <span>${hydrationMessage || hydrationState}</span>
          </div>
        `
        : '';

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

        ${
          isDisconnected
            ? `
          <div class="jp-DataingWidget-connect-section">
            <p>Not connected to Dataing backend.</p>
            <button class="jp-DataingWidget-connect-btn">Connect</button>
          </div>
        `
            : ''
        }

        ${
          isConnected
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

          <div class="jp-DataingWidget-section jp-DataingWidget-investigations-section">
            <label>
              Recent Investigations
              <button class="jp-DataingWidget-refresh-btn" title="Refresh list">↻</button>
            </label>
            ${hydrationIndicator}
            <div class="jp-DataingWidget-investigations-list">
              ${investigationsHtml}
            </div>
          </div>
        `
            : ''
        }

        ${
          connectionState === 'checking'
            ? `
          <div class="jp-DataingWidget-checking">
            <span class="jp-DataingWidget-spinner"></span>
            <span>Checking connection...</span>
          </div>
        `
            : ''
        }

        ${
          errorMessage
            ? `
          <div class="jp-DataingWidget-error">
            ${errorMessage}
          </div>
        `
            : ''
        }

        <div class="jp-DataingWidget-timeline" id="dataing-timeline">
          <!-- Timeline events rendered here -->
        </div>
      </div>
    `;

    // Add event listeners
    const connectBtn = this._contentWidget.node.querySelector(
      '.jp-DataingWidget-connect-btn'
    );
    if (connectBtn) {
      connectBtn.addEventListener('click', () => this.showWizard());
    }

    const editBtn = this._contentWidget.node.querySelector(
      '.jp-DataingWidget-edit-btn'
    );
    if (editBtn) {
      editBtn.addEventListener('click', () => this.showWizard());
    }

    const copyBtn = this._contentWidget.node.querySelector(
      '.jp-DataingWidget-copy-btn'
    );
    if (copyBtn) {
      copyBtn.addEventListener('click', () => this._copySnippet());
    }

    const detachBtn = this._contentWidget.node.querySelector(
      '.jp-DataingWidget-detach'
    );
    if (detachBtn) {
      detachBtn.addEventListener('click', () => this.detach());
    }

    // Hydrate button listeners
    const hydrateBtns = this._contentWidget.node.querySelectorAll(
      '.jp-DataingWidget-hydrate-btn'
    );
    hydrateBtns.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const target = e.currentTarget as HTMLElement;
        const investigationId = target.getAttribute('data-investigation-id');
        if (investigationId) {
          void this.hydrate(investigationId);
        }
      });
    });

    // Refresh button listener
    const refreshBtn = this._contentWidget.node.querySelector(
      '.jp-DataingWidget-refresh-btn'
    );
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        void this.fetchInvestigations();
      });
    }
  }

  /**
   * Render timeline events
   */
  private _renderTimeline(): void {
    const timelineEl = this._contentWidget.node.querySelector('#dataing-timeline');
    if (!timelineEl) return;

    const eventColors: Record<string, string> = {
      run_started: '#3b82f6',
      run_progress: '#8b5cf6',
      run_evidence: '#10b981',
      run_completed: '#10b981',
      run_failed: '#ef4444',
      run_heartbeat: '#6b7280'
    };

    const eventIcons: Record<string, string> = {
      run_started: '\uD83D\uDE80', // rocket
      run_progress: '\u23F3', // hourglass
      run_evidence: '\uD83D\uDCCB', // clipboard
      run_completed: '\u2705', // check mark
      run_failed: '\u274C', // cross mark
      run_heartbeat: '\uD83D\uDC93' // heartbeat
    };

    timelineEl.innerHTML = this._state.timeline
      .map(
        (evt) => `
        <div class="jp-DataingWidget-event" style="border-left-color: ${eventColors[evt.event] || '#6b7280'};">
          <span class="jp-DataingWidget-event-icon">${eventIcons[evt.event] || '\u2022'}</span>
          <span class="jp-DataingWidget-event-type">${evt.event}</span>
          <span class="jp-DataingWidget-event-seq">#${evt.seq}</span>
        </div>
      `
      )
      .join('');
  }

  /**
   * Dispose of the widget
   */
  dispose(): void {
    this.stopStream();
    super.dispose();
  }
}
