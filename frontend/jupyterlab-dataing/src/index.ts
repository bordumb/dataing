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

import { URLExt } from '@jupyterlab/coreutils';

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
  showStatusBar: true
};

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
  optional: [ISettingRegistry, IStatusBar, ICommandPalette, ILayoutRestorer],
  activate: async (
    app: JupyterFrontEnd,
    settingRegistry: ISettingRegistry | null,
    statusBar: IStatusBar | null,
    palette: ICommandPalette | null,
    restorer: ILayoutRestorer | null
  ) => {
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

    // Function to update connection state
    const updateConnectionState = async () => {
      // Guard concurrent checks
      if (checkInFlight) {
        return;
      }

      checkInFlight = true;
      state.connectionState = 'checking';
      state.lastCheck = new Date();

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

        state.backendUrl = result.backendUrl || settings.backendUrl;

        if (result.backendOk) {
          // Fully connected
          state.connectionState = 'connected';
          state.errorMessage = null;
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

      checkTimerId = setTimeout(async () => {
        await updateConnectionState();
        scheduleNextCheck();
      }, settings.connectionCheckInterval * 1000);
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
            settings.backendUrl = backendUrl;
            state.backendUrl = backendUrl;
          }

          const autoConnect = settingsObj.get('autoConnect').composite;
          if (typeof autoConnect === 'boolean') {
            settings.autoConnect = autoConnect;
          }

          const checkInterval = settingsObj.get('connectionCheckInterval').composite;
          if (typeof checkInterval === 'number' && checkInterval > 0) {
            settings.connectionCheckInterval = checkInterval;
          }

          const showStatusBar = settingsObj.get('showStatusBar').composite;
          if (typeof showStatusBar === 'boolean') {
            settings.showStatusBar = showStatusBar;
          }
        };

        // Initial load
        loadAllSettings();

        // Watch for settings changes - reload all and reschedule
        settingsObj.changed.connect(() => {
          const oldAutoConnect = settings.autoConnect;
          const oldInterval = settings.connectionCheckInterval;

          loadAllSettings();

          // If autoConnect changed or interval changed, reschedule
          if (oldAutoConnect !== settings.autoConnect || oldInterval !== settings.connectionCheckInterval) {
            scheduleNextCheck(); // Will clear old timer and respect new settings
          }

          // Re-check connection if settings changed
          void updateConnectionState();
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
      await updateConnectionState();
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
