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

import { PageConfig, URLExt } from '@jupyterlab/coreutils';

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
 * Build URL with Jupyter base_url
 */
function buildServerUrl(path: string): string {
  const baseUrl = PageConfig.getBaseUrl();
  return URLExt.join(baseUrl, path);
}

/**
 * Check connection via server extension proxy
 */
async function checkConnection(
  abortSignal?: AbortSignal
): Promise<{
  serverExtensionOk: boolean;
  backendOk: boolean;
  backendUrl: string;
  error?: string;
}> {
  try {
    // Check server extension handshake
    const handshakeUrl = buildServerUrl('dataing/handshake');
    const handshakeResponse = await fetch(handshakeUrl, { signal: abortSignal });

    if (!handshakeResponse.ok) {
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
    const proxyUrl = buildServerUrl('dataing/proxy/health');
    const healthResponse = await fetch(proxyUrl, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: abortSignal
    });

    if (healthResponse.ok) {
      return {
        serverExtensionOk: true,
        backendOk: true,
        backendUrl
      };
    }

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

    // Initialize settings
    const settings: IDataingSettings = { ...DEFAULT_SETTINGS };

    // Initialize state
    const state: IDataingState = {
      backendUrl: settings.backendUrl,
      connectionState: 'disconnected',
      lastCheck: null,
      errorMessage: null
    };

    // Load settings if available
    if (settingRegistry) {
      try {
        const settingsObj = await settingRegistry.load(EXTENSION_ID);

        // Load all settings
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

        // Watch for settings changes
        settingsObj.changed.connect(() => {
          const newUrl = settingsObj.get('backendUrl').composite as string;
          if (newUrl && newUrl !== settings.backendUrl) {
            settings.backendUrl = newUrl;
            state.backendUrl = newUrl;
            // Re-check connection with new URL
            updateConnectionState();
          }
        });

        console.log('Dataing settings loaded:', settings);
      } catch (error) {
        console.warn('Could not load Dataing settings:', error);
      }
    }

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
        const result = await checkConnection(abortController.signal);

        state.backendUrl = result.backendUrl || settings.backendUrl;

        if (result.backendOk) {
          state.connectionState = 'connected';
          state.errorMessage = null;
        } else if (result.serverExtensionOk) {
          state.connectionState = 'error';
          state.errorMessage = result.error || 'Backend unreachable';
        } else {
          state.connectionState = 'error';
          state.errorMessage = result.error || 'Connection failed';
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          // Check was aborted, don't update state
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
      }
      checkTimerId = setTimeout(async () => {
        await updateConnectionState();
        scheduleNextCheck();
      }, settings.connectionCheckInterval * 1000);
    };

    // Add status bar widget if available and enabled
    let statusBarWidget: DataingStatusBar | null = null;

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
    }

    // Start periodic checks
    scheduleNextCheck();

    // Cleanup on app disposal
    app.commands.addCommand('dataing:cleanup', {
      execute: () => {
        if (checkTimerId !== null) {
          clearTimeout(checkTimerId);
          checkTimerId = null;
        }
        if (abortController) {
          abortController.abort();
        }
      }
    });

    console.log('Dataing JupyterLab extension activated');
  }
};

/**
 * Export the plugin as default
 */
export default plugin;
