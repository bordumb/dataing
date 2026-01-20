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
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ISettingRegistry } from '@jupyterlab/settingregistry';

import { IStatusBar } from '@jupyterlab/statusbar';

import { ServerConnection } from '@jupyterlab/services';

import { URLExt } from '@jupyterlab/coreutils';

import { DataingStatusBar } from './statusbar';

import type { IDataingState, IDataingSettings } from './types';
export type { ConnectionState, IDataingState } from './types';

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
const plugin: JupyterFrontEndPlugin<void> = {
  id: EXTENSION_ID,
  description: 'JupyterLab extension for Dataing data quality investigation',
  autoStart: true,
  optional: [ISettingRegistry, IStatusBar],
  activate: async (
    app: JupyterFrontEnd,
    settingRegistry: ISettingRegistry | null,
    statusBar: IStatusBar | null
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

    // DECLARE statusBarWidget BEFORE any callbacks that might reference it
    let statusBarWidget: DataingStatusBar | null = null;

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

      // Update status bar to show checking
      if (statusBarWidget) {
        statusBarWidget.updateState(state);
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

      // Update status bar if available
      if (statusBarWidget) {
        statusBarWidget.updateState(state);
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

    // Initial connection check if autoConnect enabled
    if (settings.autoConnect) {
      state.connectionState = 'checking';
      if (statusBarWidget) {
        statusBarWidget.updateState(state);
      }
      await updateConnectionState();
      // Start periodic checks only if autoConnect is true
      scheduleNextCheck();
    }

    // Register cleanup on shell disposed
    app.shell.disposed.connect(cleanup);

    console.log('Dataing JupyterLab extension activated');
  }
};

/**
 * Export the plugin as default
 */
export default plugin;
