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

import { DataingStatusBar } from './statusbar';

/**
 * Extension ID
 */
const EXTENSION_ID = '@dataing/jupyterlab-dataing:plugin';

/**
 * Default settings
 */
const DEFAULT_BACKEND_URL = 'http://localhost:8000';

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
 * Check connection to the backend
 */
async function checkConnection(backendUrl: string): Promise<{
  connected: boolean;
  error?: string;
}> {
  try {
    // First try the server extension handshake
    const handshakeResponse = await fetch('/dataing/handshake');
    if (handshakeResponse.ok) {
      const data = await handshakeResponse.json();
      return { connected: true };
    }

    // Fall back to direct backend health check
    const healthResponse = await fetch(`${backendUrl}/health`, {
      method: 'GET',
      headers: { Accept: 'application/json' }
    });

    if (healthResponse.ok) {
      return { connected: true };
    }

    return { connected: false, error: `Status: ${healthResponse.status}` };
  } catch (error) {
    return {
      connected: false,
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

    // Initialize state
    const state: IDataingState = {
      backendUrl: DEFAULT_BACKEND_URL,
      connectionState: 'checking',
      lastCheck: null,
      errorMessage: null
    };

    // Load settings if available
    if (settingRegistry) {
      try {
        const settings = await settingRegistry.load(EXTENSION_ID);

        // Get backend URL from settings
        const backendUrl = settings.get('backendUrl').composite as string;
        if (backendUrl) {
          state.backendUrl = backendUrl;
        }

        // Watch for settings changes
        settings.changed.connect(() => {
          const newUrl = settings.get('backendUrl').composite as string;
          if (newUrl && newUrl !== state.backendUrl) {
            state.backendUrl = newUrl;
            // Re-check connection with new URL
            updateConnectionState();
          }
        });

        console.log('Dataing settings loaded:', state.backendUrl);
      } catch (error) {
        console.warn('Could not load Dataing settings:', error);
      }
    }

    // Function to update connection state
    const updateConnectionState = async () => {
      state.connectionState = 'checking';
      state.lastCheck = new Date();

      const result = await checkConnection(state.backendUrl);

      if (result.connected) {
        state.connectionState = 'connected';
        state.errorMessage = null;
      } else {
        state.connectionState = 'error';
        state.errorMessage = result.error || 'Connection failed';
      }

      // Update status bar if available
      if (statusBarWidget) {
        statusBarWidget.updateState(state);
      }
    };

    // Add status bar widget if available
    let statusBarWidget: DataingStatusBar | null = null;

    if (statusBar) {
      statusBarWidget = new DataingStatusBar(state);

      statusBar.registerStatusItem(EXTENSION_ID, {
        item: statusBarWidget,
        align: 'right',
        rank: 100
      });

      console.log('Dataing status bar widget added');
    }

    // Initial connection check
    await updateConnectionState();

    // Periodic connection check (every 30 seconds)
    setInterval(updateConnectionState, 30000);

    console.log('Dataing JupyterLab extension activated');
  }
};

/**
 * Export the plugin as default
 */
export default plugin;
