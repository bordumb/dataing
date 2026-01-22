/**
 * Connection Wizard Lumino Widget wrapper.
 *
 * Wraps the React ConnectionWizard component in a Lumino ReactWidget
 * for integration with JupyterLab's panel system.
 */
import * as React from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { type CredentialMode, type IConnectionWizardProps } from './components/ConnectionWizard';
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
export declare class ConnectionWizardWidget extends ReactWidget {
    private _options;
    constructor(options: IConnectionWizardWidgetOptions);
    /**
     * Update options (e.g., when recent URLs change)
     */
    updateOptions(options: Partial<IConnectionWizardWidgetOptions>): void;
    /**
     * Render the React component
     */
    render(): React.ReactElement<IConnectionWizardProps>;
}
/**
 * Create a new ConnectionWizardWidget
 */
export declare function createConnectionWizardWidget(options: IConnectionWizardWidgetOptions): ConnectionWizardWidget;
