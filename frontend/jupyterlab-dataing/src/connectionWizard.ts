/**
 * Connection Wizard Lumino Widget wrapper.
 *
 * Wraps the React ConnectionWizard component in a Lumino ReactWidget
 * for integration with JupyterLab's panel system.
 */

import * as React from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import {
  ConnectionWizard,
  type CredentialMode,
  type IConnectionWizardProps
} from './components/ConnectionWizard';

/**
 * Props for the ConnectionWizardWidget
 */
export interface IConnectionWizardWidgetOptions {
  initialUrl?: string;
  recentUrls?: string[];
  serverBaseUrl: string;
  onConnect: (url: string, mode: CredentialMode) => void;
  onCancel: () => void;
}

/**
 * ConnectionWizardWidget - Lumino wrapper for ConnectionWizard React component.
 */
export class ConnectionWizardWidget extends ReactWidget {
  private _options: IConnectionWizardWidgetOptions;

  constructor(options: IConnectionWizardWidgetOptions) {
    super();
    this._options = options;
    this.addClass('jp-ConnectionWizardWidget');
  }

  /**
   * Update options (e.g., when recent URLs change)
   */
  updateOptions(options: Partial<IConnectionWizardWidgetOptions>): void {
    this._options = { ...this._options, ...options };
    this.update();
  }

  /**
   * Render the React component
   */
  render(): React.ReactElement<IConnectionWizardProps> {
    return React.createElement(ConnectionWizard, {
      initialUrl: this._options.initialUrl,
      recentUrls: this._options.recentUrls,
      serverBaseUrl: this._options.serverBaseUrl,
      onConnect: this._options.onConnect,
      onCancel: this._options.onCancel
    });
  }
}

/**
 * Create a new ConnectionWizardWidget
 */
export function createConnectionWizardWidget(
  options: IConnectionWizardWidgetOptions
): ConnectionWizardWidget {
  return new ConnectionWizardWidget(options);
}
