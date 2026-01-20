/**
 * Status bar widget for Dataing connection state.
 */

import { Widget } from '@lumino/widgets';
import { IDataingState, ConnectionState } from './index';

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
      this._showDetails();
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
        this._indicator.style.backgroundColor = '#10b981'; // Green
        this.title.caption = `Connected to ${this._state.backendUrl}`;
        break;

      case 'disconnected':
        this.addClass(STATUS_DISCONNECTED_CLASS);
        this._text.textContent = 'Dataing';
        this._indicator.style.backgroundColor = '#6b7280'; // Gray
        this.title.caption = 'Disconnected';
        break;

      case 'checking':
        this.addClass(STATUS_CHECKING_CLASS);
        this._text.textContent = 'Dataing...';
        this._indicator.style.backgroundColor = '#3b82f6'; // Blue
        this.title.caption = 'Checking connection...';
        break;

      case 'error':
        this.addClass(STATUS_ERROR_CLASS);
        this._text.textContent = 'Dataing';
        this._indicator.style.backgroundColor = '#ef4444'; // Red
        this.title.caption = `Error: ${this._state.errorMessage || 'Unknown error'}`;
        break;
    }
  }

  /**
   * Show connection details in a dialog.
   */
  private _showDetails(): void {
    const message = `
Dataing Connection Status
========================
Backend URL: ${this._state.backendUrl}
Status: ${this._state.connectionState}
Last Check: ${this._state.lastCheck?.toLocaleTimeString() || 'Never'}
${this._state.errorMessage ? `Error: ${this._state.errorMessage}` : ''}

Configure backend URL in Settings > Advanced Settings > Dataing
    `.trim();

    alert(message);
  }
}
