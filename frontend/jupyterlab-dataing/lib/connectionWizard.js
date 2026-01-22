/**
 * Connection Wizard Lumino Widget wrapper.
 *
 * Wraps the React ConnectionWizard component in a Lumino ReactWidget
 * for integration with JupyterLab's panel system.
 */
import * as React from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ConnectionWizard } from './components/ConnectionWizard';
/**
 * ConnectionWizardWidget - Lumino wrapper for ConnectionWizard React component.
 */
export class ConnectionWizardWidget extends ReactWidget {
    constructor(options) {
        super();
        this._options = options;
        this.addClass('jp-ConnectionWizardWidget');
    }
    /**
     * Update options (e.g., when recent URLs change)
     */
    updateOptions(options) {
        this._options = { ...this._options, ...options };
        this.update();
    }
    /**
     * Render the React component
     */
    render() {
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
export function createConnectionWizardWidget(options) {
    return new ConnectionWizardWidget(options);
}
//# sourceMappingURL=connectionWizard.js.map
