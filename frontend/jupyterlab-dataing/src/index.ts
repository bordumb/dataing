/**
 * JupyterLab extension for Dataing data quality investigation.
 *
 * This extension provides:
 * - Status bar widget showing connection state
 * - Settings panel for backend URL configuration
 * - Integration with the Dataing notebook server extension
 */

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin,
  ILayoutRestorer
} from '@jupyterlab/application';

import { ISettingRegistry } from '@jupyterlab/settingregistry';

import { IStatusBar } from '@jupyterlab/statusbar';

import { ICommandPalette } from '@jupyterlab/apputils';

import { ServerConnection } from '@jupyterlab/services';

import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';

import { URLExt } from '@jupyterlab/coreutils';

import { JSONExt, type PartialJSONValue } from '@lumino/coreutils';

import { DataingStatusBar } from './statusbar';

import { DataingWidget } from './widget';

import type { IDataingState, IDataingSettings } from './types';
export type { ConnectionState, IDataingState } from './types';

/**
 * State endpoint for notebook magic sync
 */
const STATE_ENDPOINT = 'dataing/state';

/**
 * State poll interval in milliseconds
 */
const STATE_POLL_INTERVAL = 2000;

/**
 * Extension ID
 */
const EXTENSION_ID = '@dataing/jupyterlab-dataing:plugin';

/**
 * Default settings
 */
const DEFAULT_SETTINGS: IDataingSettings = {
  backendUrl: 'http://localhost:8000',
  autoConnect: true,
  connectionCheckInterval: 30,
  showStatusBar: true,
  recentUrls: [],
  workspaceId: ''
};

const MIN_CONNECTION_CHECK_INTERVAL = 5;
const MAX_CONNECTION_CHECK_INTERVAL = 300;

/**
 * Generate a UUID v4 for workspace identification
 */
function generateUUID(): string {
  // Use crypto.randomUUID if available, otherwise fallback
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for older browsers
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Maximum number of recent URLs to store
 */
const MAX_RECENT_URLS = 10;

function normalizeBackendUrl(url: string): string {
  return url.replace(/\/+$/, '');
}

/**
 * Check connection via server extension proxy using ServerConnection
 */
async function checkConnection(
  serverSettings: ServerConnection.ISettings,
  abortSignal?: AbortSignal
): Promise<{
  serverExtensionOk: boolean;
  backendOk: boolean;
  backendUrl: string;
  error?: string;
}> {
  try {
    // Check server extension handshake using ServerConnection
    const handshakeUrl = URLExt.join(serverSettings.baseUrl, 'dataing/handshake');
    const handshakeResponse = await ServerConnection.makeRequest(
      handshakeUrl,
      { signal: abortSignal },
      serverSettings
    );

    if (!handshakeResponse.ok) {
      // Could be auth issue or server extension not available
      if (handshakeResponse.status === 403 || handshakeResponse.status === 401) {
        return {
          serverExtensionOk: false,
          backendOk: false,
          backendUrl: '',
          error: 'Authentication required - please refresh the page'
        };
      }
      return {
        serverExtensionOk: false,
        backendOk: false,
        backendUrl: '',
        error: `Server extension error: ${handshakeResponse.status}`
      };
    }

    const handshakeData = await handshakeResponse.json();
    const backendUrl = handshakeData.backend_url || '';

    // Check backend via server extension proxy
    const proxyUrl = URLExt.join(serverSettings.baseUrl, 'dataing/proxy/health');
    const healthResponse = await ServerConnection.makeRequest(
      proxyUrl,
      {
        method: 'GET',
        signal: abortSignal
      },
      serverSettings
    );

    if (healthResponse.ok) {
      return {
        serverExtensionOk: true,
        backendOk: true,
        backendUrl
      };
    }

    // Server extension works but backend is unreachable
    return {
      serverExtensionOk: true,
      backendOk: false,
      backendUrl,
      error: `Backend status: ${healthResponse.status}`
    };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw error; // Re-throw abort
    }
    return {
      serverExtensionOk: false,
      backendOk: false,
      backendUrl: '',
      error: error instanceof Error ? error.message : 'Unknown error'
    };
  }
}

/**
 * Main extension plugin
 */
/**
 * Command IDs
 */
const CommandIDs = {
  open: 'dataing:open'
};

const plugin: JupyterFrontEndPlugin<void> = {
  id: EXTENSION_ID,
  description: 'JupyterLab extension for Dataing data quality investigation',
  autoStart: true,
  optional: [ISettingRegistry, IStatusBar, ICommandPalette, ILayoutRestorer, INotebookTracker],
  activate: async (
    app: JupyterFrontEnd,
    settingRegistry: ISettingRegistry | null,
    statusBar: IStatusBar | null,
    palette: ICommandPalette | null,
    restorer: ILayoutRestorer | null,
    notebookTracker: INotebookTracker | null
  ) => {
    if (typeof window !== 'undefined') {
      const globalWindow = window as unknown as Record<string, unknown>;
      if (globalWindow.__dataingJupyterlabActivated) {
        console.warn('Dataing: extension already activated, skipping duplicate instance.');
        return;
      }
      globalWindow.__dataingJupyterlabActivated = true;
    }

    console.log('Dataing JupyterLab extension is activating');

    // Get server connection settings (includes auth token handling)
    const serverSettings = ServerConnection.makeSettings();

    // Initialize settings - DECLARE FIRST before any callbacks
    const settings: IDataingSettings = { ...DEFAULT_SETTINGS };

    // Initialize state - DECLARE FIRST before any callbacks
    const state: IDataingState = {
      backendUrl: settings.backendUrl,
      connectionState: 'disconnected',
      lastCheck: null,
      errorMessage: null
    };

    // DECLARE widgets BEFORE any callbacks that might reference them
    let statusBarWidget: DataingStatusBar | null = null;
    let sidebarWidget: DataingWidget | null = null;

    // Track in-flight checks and abort controller
    let checkInFlight = false;
    let abortController: AbortController | null = null;
    let checkTimerId: ReturnType<typeof setTimeout> | null = null;
    let lastCheckedBackendUrl: string | null = null;
    let lastConnectionCheckCallMs = 0;
    const globalCheckState = (() => {
      if (typeof window === 'undefined') {
        return { inFlight: false, lastCheckMs: 0 };
      }
      const globalWindow = window as unknown as Record<string, unknown>;
      if (!globalWindow.__dataingGlobalCheckState) {
        globalWindow.__dataingGlobalCheckState = { inFlight: false, lastCheckMs: 0 };
      }
      return globalWindow.__dataingGlobalCheckState as {
        inFlight: boolean;
        lastCheckMs: number;
      };
    })();

    // Callback to add URL to recent list (set when settings loaded)
    let onConnectionSuccess: ((url: string) => Promise<void>) | null = null;

    // Function to update backend URL (set when settings loaded, used by wizard)
    let updateBackendUrlFn: ((url: string) => Promise<void>) | null = null;

    // Function to get recent URLs (set when settings loaded, used by wizard)
    let getRecentUrlsFn: (() => string[]) | null = null;

    // Function to update connection state
    const updateConnectionState = async (force = false, source = 'unknown') => {
      const now = Date.now();
      const normalizedCurrentUrl = normalizeBackendUrl(settings.backendUrl);
      const normalizedLastCheckedUrl = lastCheckedBackendUrl
        ? normalizeBackendUrl(lastCheckedBackendUrl)
        : null;
      const hasSameUrl =
        normalizedLastCheckedUrl !== null &&
        normalizedLastCheckedUrl === normalizedCurrentUrl;
      const intervalSeconds = Number.isFinite(settings.connectionCheckInterval)
        ? settings.connectionCheckInterval
        : MIN_CONNECTION_CHECK_INTERVAL;
      const minIntervalMs = Math.max(
        intervalSeconds * 1000,
        MIN_CONNECTION_CHECK_INTERVAL * 1000
      );
      const callDeltaMs = lastConnectionCheckCallMs ? now - lastConnectionCheckCallMs : null;
      lastConnectionCheckCallMs = now;
      if (callDeltaMs !== null && callDeltaMs < 1000) {
        console.warn('Dataing: rapid connection check call', {
          source,
          callDeltaMs,
          force,
          checkInFlight,
          lastCheck: state.lastCheck ? state.lastCheck.toISOString() : null,
          minIntervalMs
        });
      }

      if (
        globalCheckState.lastCheckMs &&
        now - globalCheckState.lastCheckMs < minIntervalMs
      ) {
        return;
      }
      if (globalCheckState.inFlight) {
        return;
      }
      if (
        (!force || hasSameUrl) &&
        state.lastCheck &&
        now - state.lastCheck.getTime() < minIntervalMs
      ) {
        return;
      }

      // Guard concurrent checks
      if (checkInFlight) {
        return;
      }

      checkInFlight = true;
      globalCheckState.inFlight = true;
      globalCheckState.lastCheckMs = now;
      const previousState = state.connectionState; // Track for state transition detection
      state.connectionState = 'checking';
      state.lastCheck = new Date();
      lastCheckedBackendUrl = settings.backendUrl;

      // Update widgets to show checking
      if (statusBarWidget) {
        statusBarWidget.updateState(state);
      }
      if (sidebarWidget) {
        sidebarWidget.updateFromState(state);
      }

      // Create abort controller for this check
      abortController = new AbortController();

      try {
        const result = await checkConnection(serverSettings, abortController.signal);

        const resolvedBackendUrl = result.backendUrl || settings.backendUrl;
        state.backendUrl = normalizeBackendUrl(resolvedBackendUrl);

        if (result.backendOk) {
          state.connectionState = 'connected';
          state.errorMessage = null;
          // Add to recent URLs only on state transition TO connected (not every periodic check)
          if (previousState !== 'connected' && onConnectionSuccess && state.backendUrl) {
            try {
              await onConnectionSuccess(state.backendUrl);
            } catch (error) {
              console.warn('Failed to save recent Dataing URL:', error);
            }
          }
        } else if (result.serverExtensionOk) {
          // Server extension ok but backend unreachable = disconnected
          state.connectionState = 'disconnected';
          state.errorMessage = result.error || 'Backend unreachable';
        } else {
          // Server extension failed = error
          state.connectionState = 'error';
          state.errorMessage = result.error || 'Connection failed';
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          // Check was aborted, don't update state
          checkInFlight = false;
          abortController = null;
          return;
        }
        state.connectionState = 'error';
        state.errorMessage = error instanceof Error ? error.message : 'Unknown error';
      } finally {
        checkInFlight = false;
        globalCheckState.inFlight = false;
        abortController = null;
      }

      // Update widgets if available
      if (statusBarWidget) {
        statusBarWidget.updateState(state);
      }
      if (sidebarWidget) {
        sidebarWidget.updateFromState(state);
      }
    };

    // Schedule next check using setTimeout (self-scheduling)
    const scheduleNextCheck = () => {
      if (checkTimerId !== null) {
        clearTimeout(checkTimerId);
        checkTimerId = null;
      }

      // Only schedule if autoConnect is enabled
      if (!settings.autoConnect) {
        return;
      }

      const intervalSeconds = Number.isFinite(settings.connectionCheckInterval)
        ? settings.connectionCheckInterval
        : MIN_CONNECTION_CHECK_INTERVAL;
      const intervalMs = Math.max(
        intervalSeconds * 1000,
        MIN_CONNECTION_CHECK_INTERVAL * 1000
      );

      checkTimerId = setTimeout(async () => {
        await updateConnectionState(false, 'timer');
        scheduleNextCheck();
      }, intervalMs);
    };

    // Cleanup function
    const cleanup = () => {
      if (checkTimerId !== null) {
        clearTimeout(checkTimerId);
        checkTimerId = null;
      }
      if (abortController) {
        abortController.abort();
      }
    };

    // Load settings if available
    if (settingRegistry) {
      try {
        const settingsObj = await settingRegistry.load(EXTENSION_ID);

        // Helper to load all settings
        const loadAllSettings = () => {
          const backendUrl = settingsObj.get('backendUrl').composite as string;
          if (backendUrl) {
            const normalizedUrl = normalizeBackendUrl(backendUrl);
            settings.backendUrl = normalizedUrl;
            state.backendUrl = normalizedUrl;
          }

          const autoConnect = settingsObj.get('autoConnect').composite;
          if (typeof autoConnect === 'boolean') {
            settings.autoConnect = autoConnect;
          }

          const checkInterval = settingsObj.get('connectionCheckInterval').composite;
          if (typeof checkInterval === 'number' && Number.isFinite(checkInterval)) {
            const clampedInterval = Math.min(
              Math.max(checkInterval, MIN_CONNECTION_CHECK_INTERVAL),
              MAX_CONNECTION_CHECK_INTERVAL
            );
            settings.connectionCheckInterval = clampedInterval;
          }

          const showStatusBar = settingsObj.get('showStatusBar').composite;
          if (typeof showStatusBar === 'boolean') {
            settings.showStatusBar = showStatusBar;
          }

          const recentUrls = settingsObj.get('recentUrls').composite;
          if (Array.isArray(recentUrls)) {
            settings.recentUrls = recentUrls as string[];
          }

          const workspaceId = settingsObj.get('workspaceId').composite;
          if (typeof workspaceId === 'string' && workspaceId) {
            settings.workspaceId = workspaceId;
          }
        };

        const internalSaveKeys = new Set(['recentUrls', 'workspaceId']);
        const pendingSettingWrites = new Map<string, PartialJSONValue>();
        let pendingInternalSaveCount = 0;

        // Function to save a single setting (tracks key to prevent re-check loop)
        const saveSetting = async (key: string, value: PartialJSONValue): Promise<void> => {
          const existingValue = settingsObj.get(key).composite;
          if (existingValue !== undefined && JSONExt.deepEqual(existingValue, value)) {
            return;
          }

          const pendingValue = pendingSettingWrites.get(key);
          if (pendingValue !== undefined && JSONExt.deepEqual(pendingValue, value)) {
            return;
          }

          pendingSettingWrites.set(key, value);
          const isInternalKey = internalSaveKeys.has(key);
          if (isInternalKey) {
            pendingInternalSaveCount += 1;
          }
          try {
            await settingsObj.set(key, value);
          } catch (error) {
            if (isInternalKey) {
              pendingInternalSaveCount = Math.max(0, pendingInternalSaveCount - 1);
            }
            console.warn(`Failed to save Dataing setting '${key}':`, error);
          } finally {
            pendingSettingWrites.delete(key);
          }
        };

        // Function to update backendUrl - expose via outer variable for wizard
        updateBackendUrlFn = async (newUrl: string): Promise<void> => {
          const normalizedUrl = normalizeBackendUrl(newUrl);
          if (!normalizedUrl) {
            return;
          }
          await saveSetting('backendUrl', normalizedUrl);
          settings.backendUrl = normalizedUrl;
          state.backendUrl = normalizedUrl;
        };

        // Function to get recent URLs - expose via outer variable for wizard
        getRecentUrlsFn = () => [...settings.recentUrls];

        // Function to add URL to recent URLs list
        const addToRecentUrls = async (url: string): Promise<void> => {
          const normalizedUrl = normalizeBackendUrl(url);
          const filtered = settings.recentUrls.filter(u => u !== normalizedUrl);
          const updated = [normalizedUrl, ...filtered].slice(0, MAX_RECENT_URLS);
          const isSame =
            updated.length === settings.recentUrls.length &&
            updated.every((value, index) => value === settings.recentUrls[index]);
          if (isSame) {
            return;
          }
          await saveSetting('recentUrls', updated);
          settings.recentUrls = updated;
        };

        // Wire up callback for connection success
        onConnectionSuccess = addToRecentUrls;

        // Initial load
        loadAllSettings();

        // Generate workspaceId on first launch if not set
        if (!settings.workspaceId) {
          const newWorkspaceId = generateUUID();
          settings.workspaceId = newWorkspaceId;
          void saveSetting('workspaceId', newWorkspaceId);
          console.log('Dataing: Generated new workspace ID:', newWorkspaceId);
        } else {
          console.log('Dataing: Using existing workspace ID:', settings.workspaceId);
        }

        // Watch for settings changes - reload all and reschedule
        settingsObj.changed.connect(() => {
          // Skip connection re-check if this is an internal save (e.g., recentUrls, workspaceId)
          const isInternalSave = pendingInternalSaveCount > 0;
          if (isInternalSave) {
            pendingInternalSaveCount = Math.max(0, pendingInternalSaveCount - 1);
          }

          const oldAutoConnect = settings.autoConnect;
          const oldInterval = settings.connectionCheckInterval;
          const oldBackendUrl = settings.backendUrl;

          loadAllSettings();

          // If autoConnect changed or interval changed, reschedule
          if (oldAutoConnect !== settings.autoConnect || oldInterval !== settings.connectionCheckInterval) {
            scheduleNextCheck(); // Will clear old timer and respect new settings
          }

          // Only re-check connection if backendUrl changed by user (not internal save)
          const normalizedOldBackendUrl = normalizeBackendUrl(oldBackendUrl);
          const normalizedNewBackendUrl = normalizeBackendUrl(settings.backendUrl);

          if (!isInternalSave && normalizedOldBackendUrl !== normalizedNewBackendUrl) {
            void updateConnectionState(true, 'settings-changed');
          }
        });

        console.log('Dataing settings loaded:', settings);
      } catch (error) {
        console.warn('Could not load Dataing settings:', error);
      }
    }

    // Add status bar widget if available and enabled
    if (statusBar && settings.showStatusBar) {
      statusBarWidget = new DataingStatusBar(state);

      statusBar.registerStatusItem(EXTENSION_ID, {
        item: statusBarWidget,
        align: 'right',
        rank: 100
      });

      console.log('Dataing status bar widget added');
    }

    // Create and add sidebar widget
    sidebarWidget = new DataingWidget();
    sidebarWidget.id = 'dataing-sidebar';
    sidebarWidget.title.iconClass = 'jp-DataingIcon';
    sidebarWidget.title.caption = 'Dataing';

    // Set server base URL for wizard API calls
    sidebarWidget.setServerBaseUrl(serverSettings.baseUrl);

    // Expose settings functions on widget for Connection Wizard to use
    if (updateBackendUrlFn) {
      sidebarWidget._updateBackendUrl = updateBackendUrlFn;
    }
    if (getRecentUrlsFn) {
      sidebarWidget._getRecentUrls = getRecentUrlsFn;
    }

    // Set workspace ID on widget
    sidebarWidget.setWorkspaceId(settings.workspaceId);

    // Track active kernel for workspace state
    let currentKernelId: string | null = null;

    // Function to update kernel tracking
    const updateActiveKernel = () => {
      if (!sidebarWidget) {
        return;
      }
      const notebookPanel = notebookTracker?.currentWidget ?? null;
      const kernel = notebookPanel?.sessionContext?.session?.kernel ?? null;
      const newKernelId = kernel?.id ?? null;

      if (newKernelId !== currentKernelId) {
        currentKernelId = newKernelId;
        sidebarWidget.setActiveKernel(newKernelId);
        console.log('Dataing: Active kernel changed:', newKernelId || '(none)');
      }
    };

    // Listen for notebook changes if tracker available
    if (notebookTracker) {
      // Track when current notebook changes
      notebookTracker.currentChanged.connect(() => {
        updateActiveKernel();
      });

      // Track when any notebook's kernel status changes
      notebookTracker.widgetAdded.connect(
        (_tracker: INotebookTracker, panel: NotebookPanel) => {
          panel.sessionContext.statusChanged.connect(() => {
            // Only update if this is the current notebook
            if (panel === notebookTracker.currentWidget) {
              updateActiveKernel();
            }
          });

          // Track kernel changes (e.g., restart, shutdown)
          panel.sessionContext.kernelChanged.connect(() => {
            if (panel === notebookTracker.currentWidget) {
              updateActiveKernel();
            }
          });
        }
      );

      // Initial update
      updateActiveKernel();
    }

    // Track widget for restoration
    if (restorer) {
      restorer.add(sidebarWidget, 'dataing-sidebar');
    }

    // Add widget to left sidebar
    app.shell.add(sidebarWidget!, 'left', { rank: 200 });

    // Add command to open/toggle sidebar
    app.commands.addCommand(CommandIDs.open, {
      label: 'Open Dataing Sidebar',
      caption: 'Open the Dataing investigation sidebar',
      execute: () => {
        if (sidebarWidget && !sidebarWidget.isAttached) {
          app.shell.add(sidebarWidget, 'left', { rank: 200 });
        }
        if (sidebarWidget) {
          app.shell.activateById(sidebarWidget.id);
        }
      }
    });

    // Add to command palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.open,
        category: 'Dataing'
      });
    }

    console.log('Dataing sidebar widget added');

    // Track state polling timer
    let statePollingTimerId: ReturnType<typeof setTimeout> | null = null;
    let lastAttachedDatasource: string | null = null;

    // Clear server state when user detaches from UI
    const clearServerState = async () => {
      try {
        const stateUrl = URLExt.join(serverSettings.baseUrl, STATE_ENDPOINT);
        await ServerConnection.makeRequest(
          stateUrl,
          { method: 'DELETE' },
          serverSettings
        );
        // Reset tracking so next attach is detected
        lastAttachedDatasource = null;
        console.log('Dataing: Server state cleared');
      } catch (error) {
        console.debug('Dataing: Failed to clear server state:', error);
      }
    };

    // Listen for widget state changes (e.g., user clicking Detach)
    sidebarWidget.stateChanged.connect((_, widgetState) => {
      // If user detached from UI (not from polling), clear server state
      if (widgetState.attachedDatasource === null && lastAttachedDatasource !== null) {
        void clearServerState();
      }
    });

    // Poll notebook state from server extension
    const pollNotebookState = async () => {
      try {
        const stateUrl = URLExt.join(serverSettings.baseUrl, STATE_ENDPOINT);
        const response = await ServerConnection.makeRequest(
          stateUrl,
          { method: 'GET' },
          serverSettings
        );

        if (response.ok) {
          const stateData = await response.json();
          const attachedDatasource = stateData.attached_datasource as string | null;

          // Only update if changed to avoid unnecessary re-renders
          if (attachedDatasource !== lastAttachedDatasource && sidebarWidget) {
            lastAttachedDatasource = attachedDatasource;

            if (attachedDatasource) {
              console.log('Dataing: Attached datasource updated:', attachedDatasource);
              sidebarWidget.attach(attachedDatasource);
            } else {
              console.log('Dataing: Datasource detached');
              sidebarWidget.detach();
            }
          }

          // Log current run if present
          const currentRunId = stateData.current_run_id as string | null;
          if (currentRunId) {
            console.log('Dataing: Current run:', currentRunId);
          }
        }
      } catch (error) {
        // State endpoint not available - that's OK, it's optional
        console.debug('Dataing state poll failed:', error);
      }
    };

    // Schedule state polling
    const scheduleStatePoll = () => {
      if (statePollingTimerId !== null) {
        clearTimeout(statePollingTimerId);
        statePollingTimerId = null;
      }

      statePollingTimerId = setTimeout(async () => {
        await pollNotebookState();
        scheduleStatePoll();
      }, STATE_POLL_INTERVAL);
    };

    // Cleanup function for state polling
    const cleanupStatePoll = () => {
      if (statePollingTimerId !== null) {
        clearTimeout(statePollingTimerId);
        statePollingTimerId = null;
      }
    };

    // Initial connection check if autoConnect enabled
    if (settings.autoConnect) {
      state.connectionState = 'checking';
      if (statusBarWidget) {
        statusBarWidget.updateState(state);
      }
      if (sidebarWidget) {
        sidebarWidget.updateFromState(state);
      }
      await updateConnectionState(false, 'initial');
      // Start periodic checks only if autoConnect is true
      scheduleNextCheck();
    }

    // Start polling notebook state (regardless of autoConnect)
    await pollNotebookState();
    scheduleStatePoll();

    // Register cleanup on shell disposed
    app.shell.disposed.connect(() => {
      cleanup();
      cleanupStatePoll();
    });

    console.log('Dataing JupyterLab extension activated');
  }
};

/**
 * Export the plugin as default
 */
export default plugin;
