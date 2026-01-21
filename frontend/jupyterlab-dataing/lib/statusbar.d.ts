/**
 * Status bar widget for Dataing connection state.
 */
import { Widget } from '@lumino/widgets';
import type { IDataingState } from './types';
/**
 * Status bar widget showing Dataing connection state.
 */
export declare class DataingStatusBar extends Widget {
    private _state;
    private _indicator;
    private _text;
    constructor(initialState: IDataingState);
    /**
     * Update the widget state.
     */
    updateState(newState: IDataingState): void;
    /**
     * Update the display based on current state.
     */
    private _updateDisplay;
    /**
     * Show connection details in a dialog (XSS-safe using textContent).
     */
    private _showDetails;
}
