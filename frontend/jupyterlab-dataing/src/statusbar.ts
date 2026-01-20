/**
 * Status bar widget for Dataing connection state.
 */

import { Widget } from '@lumino/widgets';

import { showDialog, Dialog } from '@jupyterlab/apputils';

import type { IDataingState } from './types';

/**
 * CSS class names
 */
const STATUS_CLASS = 'jp-Dataing-status';
const STATUS_CONNECTED_CLASS = 'jp-Dataing-status-connected';
const STATUS_DISCONNECTED_CLASS = 'jp-Dataing-status-disconnected';
const STATUS_CHECKING_CLASS = 'jp-Dataing-status-checking';
const STATUS_ERROR_CLASS = 'jp-Dataing-status-error';

/**
 * Status bar widget showing Dataing connection state.
 */
export class DataingStatusBar extends Widget {
  private _state: IDataingState;
  private _indicator: HTMLSpanElement;
  private _text: HTMLSpanElement;

  constructor(initialState: IDataingState) {
    super();
    this._state = { ...initialState };

    this.addClass(STATUS_CLASS);
    this.id = 'dataing-status-bar';
    this.title.caption = 'Dataing Connection Status';

    // Create indicator dot
    this._indicator = document.createElement('span');
    this._indicator.className = 'jp-Dataing-status-indicator';
    this.node.appendChild(this._indicator);

    // Create text label
    this._text = document.createElement('span');
    this._text.className = 'jp-Dataing-status-text';
    this.node.appendChild(this._text);

    // Set initial state
    this._updateDisplay();

    // Handle click to show details
    this.node.addEventListener('click', () => {
      void this._showDetails();
    });
  }

  /**
   * Update the widget state.
   */
  updateState(newState: IDataingState): void {
    this._state = { ...newState };
    this._updateDisplay();
  }

  /**
   * Update the display based on current state.
   */
  private _updateDisplay(): void {
    // Remove all state classes
    this.removeClass(STATUS_CONNECTED_CLASS);
    this.removeClass(STATUS_DISCONNECTED_CLASS);
    this.removeClass(STATUS_CHECKING_CLASS);
    this.removeClass(STATUS_ERROR_CLASS);

    // Add appropriate class and update text
    switch (this._state.connectionState) {
      case 'connected':
        this.addClass(STATUS_CONNECTED_CLASS);
        this._text.textContent = 'Dataing';
        this.title.caption = `Connected to ${this._state.backendUrl}`;
        break;

      case 'disconnected':
        this.addClass(STATUS_DISCONNECTED_CLASS);
        this._text.textContent = 'Dataing';
        this.title.caption = 'Disconnected';
        break;

      case 'checking':
        this.addClass(STATUS_CHECKING_CLASS);
        this._text.textContent = 'Dataing...';
        this.title.caption = 'Checking connection...';
        break;

      case 'error':
        this.addClass(STATUS_ERROR_CLASS);
        this._text.textContent = 'Dataing';
        this.title.caption = `Error: ${this._state.errorMessage || 'Unknown error'}`;
        break;
    }
  }

  /**
   * Show connection details in a dialog (XSS-safe using textContent).
   */
  private async _showDetails(): Promise<void> {
    const statusText = this._state.connectionState === 'connected'
      ? 'Connected'
      : this._state.connectionState === 'checking'
        ? 'Checking...'
        : this._state.connectionState === 'disconnected'
          ? 'Disconnected'
          : 'Error';

    // Build dialog content safely using DOM methods (no innerHTML)
    const content = document.createElement('div');
    content.className = 'dataing-details';
    content.style.cssText = 'font-family: var(--jp-ui-font-family);';

    const dl = document.createElement('dl');
    dl.style.cssText = 'display: grid; grid-template-columns: auto 1fr; gap: 8px; margin: 0;';

    // Backend URL
    const dtUrl = document.createElement('dt');
    dtUrl.style.cssText = 'font-weight: bold; color: var(--jp-ui-font-color1);';
    dtUrl.textContent = 'Backend URL';
    const ddUrl = document.createElement('dd');
    ddUrl.style.cssText = 'margin: 0; color: var(--jp-ui-font-color2); word-break: break-all;';
    ddUrl.textContent = this._state.backendUrl || 'Not configured';
    dl.appendChild(dtUrl);
    dl.appendChild(ddUrl);

    // Status
    const dtStatus = document.createElement('dt');
    dtStatus.style.cssText = 'font-weight: bold; color: var(--jp-ui-font-color1);';
    dtStatus.textContent = 'Status';
    const ddStatus = document.createElement('dd');
    ddStatus.style.cssText = 'margin: 0; color: var(--jp-ui-font-color2);';
    ddStatus.textContent = statusText;
    dl.appendChild(dtStatus);
    dl.appendChild(ddStatus);

    // Last Check
    const dtLastCheck = document.createElement('dt');
    dtLastCheck.style.cssText = 'font-weight: bold; color: var(--jp-ui-font-color1);';
    dtLastCheck.textContent = 'Last Check';
    const ddLastCheck = document.createElement('dd');
    ddLastCheck.style.cssText = 'margin: 0; color: var(--jp-ui-font-color2);';
    ddLastCheck.textContent = this._state.lastCheck?.toLocaleTimeString() || 'Never';
    dl.appendChild(dtLastCheck);
    dl.appendChild(ddLastCheck);

    // Error (if any)
    if (this._state.errorMessage) {
      const dtError = document.createElement('dt');
      dtError.style.cssText = 'font-weight: bold; color: var(--jp-ui-font-color1);';
      dtError.textContent = 'Error';
      const ddError = document.createElement('dd');
      ddError.style.cssText = 'margin: 0; color: var(--jp-error-color1);';
      ddError.textContent = this._state.errorMessage;
      dl.appendChild(dtError);
      dl.appendChild(ddError);
    }

    content.appendChild(dl);

    // Settings hint
    const hint = document.createElement('p');
    hint.style.cssText = 'margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--jp-border-color1); font-size: 12px; color: var(--jp-ui-font-color2);';
    hint.textContent = 'Configure backend URL in Settings > Advanced Settings Editor > Dataing';
    content.appendChild(hint);

    await showDialog({
      title: 'Dataing Connection Status',
      body: new Widget({ node: content }),
      buttons: [Dialog.okButton()]
    });
  }
}
