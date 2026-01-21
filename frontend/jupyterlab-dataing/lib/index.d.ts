/**
 * JupyterLab extension for Dataing data quality investigation.
 *
 * This extension provides:
 * - Status bar widget showing connection state
 * - Settings panel for backend URL configuration
 * - Integration with the Dataing notebook server extension
 */
import { JupyterFrontEndPlugin } from '@jupyterlab/application';
export type { ConnectionState, IDataingState } from './types';
declare const plugin: JupyterFrontEndPlugin<void>;
/**
 * Export the plugin as default
 */
export default plugin;
