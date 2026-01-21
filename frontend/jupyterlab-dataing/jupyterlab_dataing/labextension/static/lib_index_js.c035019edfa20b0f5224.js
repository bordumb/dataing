"use strict";
(self["webpackChunk_dataing_jupyterlab_dataing"] = self["webpackChunk_dataing_jupyterlab_dataing"] || []).push([["lib_index_js"],{

/***/ "./lib/index.js"
/*!**********************!*\
  !*** ./lib/index.js ***!
  \**********************/
(__unused_webpack_module, __webpack_exports__, __webpack_require__) {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   "default": () => (__WEBPACK_DEFAULT_EXPORT__)
/* harmony export */ });
/* harmony import */ var _jupyterlab_application__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @jupyterlab/application */ "webpack/sharing/consume/default/@jupyterlab/application");
/* harmony import */ var _jupyterlab_application__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_application__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _jupyterlab_settingregistry__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @jupyterlab/settingregistry */ "webpack/sharing/consume/default/@jupyterlab/settingregistry");
/* harmony import */ var _jupyterlab_settingregistry__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_settingregistry__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _jupyterlab_statusbar__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @jupyterlab/statusbar */ "webpack/sharing/consume/default/@jupyterlab/statusbar");
/* harmony import */ var _jupyterlab_statusbar__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_statusbar__WEBPACK_IMPORTED_MODULE_2__);
/* harmony import */ var _jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! @jupyterlab/apputils */ "webpack/sharing/consume/default/@jupyterlab/apputils");
/* harmony import */ var _jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_3___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_3__);
/* harmony import */ var _jupyterlab_services__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! @jupyterlab/services */ "webpack/sharing/consume/default/@jupyterlab/services");
/* harmony import */ var _jupyterlab_services__WEBPACK_IMPORTED_MODULE_4___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_services__WEBPACK_IMPORTED_MODULE_4__);
/* harmony import */ var _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! @jupyterlab/coreutils */ "webpack/sharing/consume/default/@jupyterlab/coreutils");
/* harmony import */ var _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_5___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_5__);
/* harmony import */ var _statusbar__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! ./statusbar */ "./lib/statusbar.js");
/* harmony import */ var _widget__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! ./widget */ "./lib/widget.js");
/**
 * JupyterLab extension for Dataing data quality investigation.
 *
 * This extension provides:
 * - Status bar widget showing connection state
 * - Settings panel for backend URL configuration
 * - Integration with the Dataing notebook server extension
 */








/**
 * State endpoint for notebook magic sync
 */
const STATE_ENDPOINT = 'dataing/state';
/**
 * State poll interval in milliseconds
 */
const STATE_POLL_INTERVAL = 2000;
/**
 * Extension ID
 */
const EXTENSION_ID = '@dataing/jupyterlab-dataing:plugin';
/**
 * Default settings
 */
const DEFAULT_SETTINGS = {
    backendUrl: 'http://localhost:8000',
    autoConnect: true,
    connectionCheckInterval: 30,
    showStatusBar: true
};
/**
 * Check connection via server extension proxy using ServerConnection
 */
async function checkConnection(serverSettings, abortSignal) {
    try {
        // Check server extension handshake using ServerConnection
        const handshakeUrl = _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_5__.URLExt.join(serverSettings.baseUrl, 'dataing/handshake');
        const handshakeResponse = await _jupyterlab_services__WEBPACK_IMPORTED_MODULE_4__.ServerConnection.makeRequest(handshakeUrl, { signal: abortSignal }, serverSettings);
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
        const proxyUrl = _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_5__.URLExt.join(serverSettings.baseUrl, 'dataing/proxy/health');
        const healthResponse = await _jupyterlab_services__WEBPACK_IMPORTED_MODULE_4__.ServerConnection.makeRequest(proxyUrl, {
            method: 'GET',
            signal: abortSignal
        }, serverSettings);
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
    }
    catch (error) {
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
/**
 * Command IDs
 */
const CommandIDs = {
    open: 'dataing:open'
};
const plugin = {
    id: EXTENSION_ID,
    description: 'JupyterLab extension for Dataing data quality investigation',
    autoStart: true,
    optional: [_jupyterlab_settingregistry__WEBPACK_IMPORTED_MODULE_1__.ISettingRegistry, _jupyterlab_statusbar__WEBPACK_IMPORTED_MODULE_2__.IStatusBar, _jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_3__.ICommandPalette, _jupyterlab_application__WEBPACK_IMPORTED_MODULE_0__.ILayoutRestorer],
    activate: async (app, settingRegistry, statusBar, palette, restorer) => {
        console.log('Dataing JupyterLab extension is activating');
        // Get server connection settings (includes auth token handling)
        const serverSettings = _jupyterlab_services__WEBPACK_IMPORTED_MODULE_4__.ServerConnection.makeSettings();
        // Initialize settings - DECLARE FIRST before any callbacks
        const settings = { ...DEFAULT_SETTINGS };
        // Initialize state - DECLARE FIRST before any callbacks
        const state = {
            backendUrl: settings.backendUrl,
            connectionState: 'disconnected',
            lastCheck: null,
            errorMessage: null
        };
        // DECLARE widgets BEFORE any callbacks that might reference them
        let statusBarWidget = null;
        let sidebarWidget = null;
        // Track in-flight checks and abort controller
        let checkInFlight = false;
        let abortController = null;
        let checkTimerId = null;
        // Function to update connection state
        const updateConnectionState = async () => {
            // Guard concurrent checks
            if (checkInFlight) {
                return;
            }
            checkInFlight = true;
            state.connectionState = 'checking';
            state.lastCheck = new Date();
            // Update widgets to show checking
            if (statusBarWidget) {
                statusBarWidget.updateState(state);
            }
            if (sidebarWidget) {
                sidebarWidget.updateFromState(state);
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
                }
                else if (result.serverExtensionOk) {
                    // Server extension ok but backend unreachable = disconnected
                    state.connectionState = 'disconnected';
                    state.errorMessage = result.error || 'Backend unreachable';
                }
                else {
                    // Server extension failed = error
                    state.connectionState = 'error';
                    state.errorMessage = result.error || 'Connection failed';
                }
            }
            catch (error) {
                if (error instanceof Error && error.name === 'AbortError') {
                    // Check was aborted, don't update state
                    checkInFlight = false;
                    abortController = null;
                    return;
                }
                state.connectionState = 'error';
                state.errorMessage = error instanceof Error ? error.message : 'Unknown error';
            }
            finally {
                checkInFlight = false;
                abortController = null;
            }
            // Update widgets if available
            if (statusBarWidget) {
                statusBarWidget.updateState(state);
            }
            if (sidebarWidget) {
                sidebarWidget.updateFromState(state);
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
                    const backendUrl = settingsObj.get('backendUrl').composite;
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
            }
            catch (error) {
                console.warn('Could not load Dataing settings:', error);
            }
        }
        // Add status bar widget if available and enabled
        if (statusBar && settings.showStatusBar) {
            statusBarWidget = new _statusbar__WEBPACK_IMPORTED_MODULE_6__.DataingStatusBar(state);
            statusBar.registerStatusItem(EXTENSION_ID, {
                item: statusBarWidget,
                align: 'right',
                rank: 100
            });
            console.log('Dataing status bar widget added');
        }
        // Create and add sidebar widget
        sidebarWidget = new _widget__WEBPACK_IMPORTED_MODULE_7__.DataingWidget();
        sidebarWidget.id = 'dataing-sidebar';
        sidebarWidget.title.iconClass = 'jp-DataingIcon';
        sidebarWidget.title.caption = 'Dataing';
        // Track widget for restoration
        if (restorer) {
            restorer.add(sidebarWidget, 'dataing-sidebar');
        }
        // Add widget to left sidebar
        app.shell.add(sidebarWidget, 'left', { rank: 200 });
        // Add command to open/toggle sidebar
        app.commands.addCommand(CommandIDs.open, {
            label: 'Open Dataing Sidebar',
            caption: 'Open the Dataing investigation sidebar',
            execute: () => {
                if (sidebarWidget && !sidebarWidget.isAttached) {
                    app.shell.add(sidebarWidget, 'left', { rank: 200 });
                }
                if (sidebarWidget) {
                    app.shell.activateById(sidebarWidget.id);
                }
            }
        });
        // Add to command palette
        if (palette) {
            palette.addItem({
                command: CommandIDs.open,
                category: 'Dataing'
            });
        }
        console.log('Dataing sidebar widget added');
        // Track state polling timer
        let statePollingTimerId = null;
        let lastAttachedDatasource = null;
        // Clear server state when user detaches from UI
        const clearServerState = async () => {
            try {
                const stateUrl = _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_5__.URLExt.join(serverSettings.baseUrl, STATE_ENDPOINT);
                await _jupyterlab_services__WEBPACK_IMPORTED_MODULE_4__.ServerConnection.makeRequest(stateUrl, { method: 'DELETE' }, serverSettings);
                // Reset tracking so next attach is detected
                lastAttachedDatasource = null;
                console.log('Dataing: Server state cleared');
            }
            catch (error) {
                console.debug('Dataing: Failed to clear server state:', error);
            }
        };
        // Listen for widget state changes (e.g., user clicking Detach)
        sidebarWidget.stateChanged.connect((_, widgetState) => {
            // If user detached from UI (not from polling), clear server state
            if (widgetState.attachedDatasource === null && lastAttachedDatasource !== null) {
                void clearServerState();
            }
        });
        // Poll notebook state from server extension
        const pollNotebookState = async () => {
            try {
                const stateUrl = _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_5__.URLExt.join(serverSettings.baseUrl, STATE_ENDPOINT);
                const response = await _jupyterlab_services__WEBPACK_IMPORTED_MODULE_4__.ServerConnection.makeRequest(stateUrl, { method: 'GET' }, serverSettings);
                if (response.ok) {
                    const stateData = await response.json();
                    const attachedDatasource = stateData.attached_datasource;
                    // Only update if changed to avoid unnecessary re-renders
                    if (attachedDatasource !== lastAttachedDatasource && sidebarWidget) {
                        lastAttachedDatasource = attachedDatasource;
                        if (attachedDatasource) {
                            console.log('Dataing: Attached datasource updated:', attachedDatasource);
                            sidebarWidget.attach(attachedDatasource);
                        }
                        else {
                            console.log('Dataing: Datasource detached');
                            sidebarWidget.detach();
                        }
                    }
                    // Log current run if present
                    const currentRunId = stateData.current_run_id;
                    if (currentRunId) {
                        console.log('Dataing: Current run:', currentRunId);
                    }
                }
            }
            catch (error) {
                // State endpoint not available - that's OK, it's optional
                console.debug('Dataing state poll failed:', error);
            }
        };
        // Schedule state polling
        const scheduleStatePoll = () => {
            if (statePollingTimerId !== null) {
                clearTimeout(statePollingTimerId);
                statePollingTimerId = null;
            }
            statePollingTimerId = setTimeout(async () => {
                await pollNotebookState();
                scheduleStatePoll();
            }, STATE_POLL_INTERVAL);
        };
        // Cleanup function for state polling
        const cleanupStatePoll = () => {
            if (statePollingTimerId !== null) {
                clearTimeout(statePollingTimerId);
                statePollingTimerId = null;
            }
        };
        // Initial connection check if autoConnect enabled
        if (settings.autoConnect) {
            state.connectionState = 'checking';
            if (statusBarWidget) {
                statusBarWidget.updateState(state);
            }
            if (sidebarWidget) {
                sidebarWidget.updateFromState(state);
            }
            await updateConnectionState();
            // Start periodic checks only if autoConnect is true
            scheduleNextCheck();
        }
        // Start polling notebook state (regardless of autoConnect)
        await pollNotebookState();
        scheduleStatePoll();
        // Register cleanup on shell disposed
        app.shell.disposed.connect(() => {
            cleanup();
            cleanupStatePoll();
        });
        console.log('Dataing JupyterLab extension activated');
    }
};
/**
 * Export the plugin as default
 */
/* harmony default export */ const __WEBPACK_DEFAULT_EXPORT__ = (plugin);


/***/ },

/***/ "./lib/statusbar.js"
/*!**************************!*\
  !*** ./lib/statusbar.js ***!
  \**************************/
(__unused_webpack_module, __webpack_exports__, __webpack_require__) {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   DataingStatusBar: () => (/* binding */ DataingStatusBar)
/* harmony export */ });
/* harmony import */ var _lumino_widgets__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @lumino/widgets */ "webpack/sharing/consume/default/@lumino/widgets");
/* harmony import */ var _lumino_widgets__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_lumino_widgets__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @jupyterlab/apputils */ "webpack/sharing/consume/default/@jupyterlab/apputils");
/* harmony import */ var _jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_1__);
/**
 * Status bar widget for Dataing connection state.
 */


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
class DataingStatusBar extends _lumino_widgets__WEBPACK_IMPORTED_MODULE_0__.Widget {
    constructor(initialState) {
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
    updateState(newState) {
        this._state = { ...newState };
        this._updateDisplay();
    }
    /**
     * Update the display based on current state.
     */
    _updateDisplay() {
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
    async _showDetails() {
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
        await (0,_jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_1__.showDialog)({
            title: 'Dataing Connection Status',
            body: new _lumino_widgets__WEBPACK_IMPORTED_MODULE_0__.Widget({ node: content }),
            buttons: [_jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_1__.Dialog.okButton()]
        });
    }
}


/***/ },

/***/ "./lib/widget.js"
/*!***********************!*\
  !*** ./lib/widget.js ***!
  \***********************/
(__unused_webpack_module, __webpack_exports__, __webpack_require__) {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   DataingWidget: () => (/* binding */ DataingWidget)
/* harmony export */ });
/* harmony import */ var _lumino_widgets__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @lumino/widgets */ "webpack/sharing/consume/default/@lumino/widgets");
/* harmony import */ var _lumino_widgets__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_lumino_widgets__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _lumino_signaling__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @lumino/signaling */ "webpack/sharing/consume/default/@lumino/signaling");
/* harmony import */ var _lumino_signaling__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_lumino_signaling__WEBPACK_IMPORTED_MODULE_1__);
/**
 * DataingWidget - Main sidebar widget for Dataing integration.
 *
 * Provides:
 * - Connection status display
 * - Datasource attach UI
 * - SSE streaming for run events
 * - Timeline rendering
 */


/**
 * DataingWidget - Main sidebar widget
 */
class DataingWidget extends _lumino_widgets__WEBPACK_IMPORTED_MODULE_0__.Widget {
    /**
     * Construct a new DataingWidget
     */
    constructor() {
        super();
        this._eventSource = null;
        this._stateChanged = new _lumino_signaling__WEBPACK_IMPORTED_MODULE_1__.Signal(this);
        this.id = 'dataing-widget';
        this.title.label = 'Dataing';
        this.title.closable = true;
        this.addClass('jp-DataingWidget');
        this._state = {
            connectionState: 'disconnected',
            backendUrl: '',
            attachedDatasource: null,
            currentRunId: null,
            timeline: [],
            errorMessage: null
        };
        this._render();
    }
    /**
     * Signal emitted when state changes
     */
    get stateChanged() {
        return this._stateChanged;
    }
    /**
     * Get current state
     */
    get state() {
        return { ...this._state };
    }
    /**
     * Update state from external source
     */
    updateFromState(appState) {
        this._state.connectionState = appState.connectionState;
        this._state.backendUrl = appState.backendUrl;
        this._state.errorMessage = appState.errorMessage;
        this._render();
        this._stateChanged.emit(this._state);
    }
    /**
     * Attach to a datasource
     */
    attach(datasourceId, name) {
        this._state.attachedDatasource = name || datasourceId;
        this._render();
        this._stateChanged.emit(this._state);
    }
    /**
     * Detach from current datasource
     */
    detach() {
        this._state.attachedDatasource = null;
        this._render();
        this._stateChanged.emit(this._state);
    }
    /**
     * Start streaming SSE events for a run
     *
     * @param runId - The run ID to stream events for
     * @param serverBaseUrl - Jupyter server base URL (for SSE proxy)
     * @param useProxy - Whether to use the server extension SSE proxy (default: true)
     */
    streamRun(runId, serverBaseUrl, useProxy = true) {
        // Close existing stream
        this.stopStream();
        this._state.currentRunId = runId;
        this._state.timeline = [];
        // Build SSE URL - use proxy to avoid CORS issues
        let sseUrl;
        if (useProxy) {
            // Use server extension SSE proxy: /dataing/sse/api/v1/runs/{id}/events
            sseUrl = `${serverBaseUrl}dataing/sse/api/v1/runs/${runId}/events`;
        }
        else {
            // Direct connection (requires CORS to be configured on backend)
            sseUrl = `${this._state.backendUrl}/api/v1/runs/${runId}/events`;
        }
        try {
            this._eventSource = new EventSource(sseUrl);
            this._eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this._state.timeline.push(data);
                    this._renderTimeline();
                    this._stateChanged.emit(this._state);
                }
                catch (e) {
                    console.error('Failed to parse SSE event:', e);
                }
            };
            this._eventSource.onerror = (error) => {
                console.error('SSE error:', error);
                this._state.errorMessage = 'Stream connection error';
                this._render();
            };
            this._eventSource.onopen = () => {
                this._state.errorMessage = null;
                this._render();
            };
        }
        catch (e) {
            this._state.errorMessage = `Failed to start stream: ${e}`;
            this._render();
        }
    }
    /**
     * Stop SSE streaming
     */
    stopStream() {
        if (this._eventSource) {
            this._eventSource.close();
            this._eventSource = null;
        }
        this._state.currentRunId = null;
    }
    /**
     * Render the widget
     */
    _render() {
        const { connectionState, backendUrl, attachedDatasource, errorMessage } = this._state;
        // Status badge color
        const statusColors = {
            connected: '#10b981',
            disconnected: '#6b7280',
            checking: '#f59e0b',
            error: '#ef4444'
        };
        this.node.innerHTML = `
      <div class="jp-DataingWidget-content">
        <div class="jp-DataingWidget-header">
          <h3>Dataing</h3>
          <span
            class="jp-DataingWidget-status"
            style="background: ${statusColors[connectionState]};"
          >
            ${connectionState}
          </span>
        </div>

        <div class="jp-DataingWidget-section">
          <label>Backend URL</label>
          <div class="jp-DataingWidget-value">${backendUrl || 'Not configured'}</div>
        </div>

        <div class="jp-DataingWidget-section">
          <label>Attached Datasource</label>
          <div class="jp-DataingWidget-value">
            ${attachedDatasource || 'None'}
            ${attachedDatasource ? '<button class="jp-DataingWidget-detach">Detach</button>' : ''}
          </div>
        </div>

        ${errorMessage ? `
          <div class="jp-DataingWidget-error">
            ${errorMessage}
          </div>
        ` : ''}

        <div class="jp-DataingWidget-timeline" id="dataing-timeline">
          <!-- Timeline events rendered here -->
        </div>
      </div>
    `;
        // Add event listeners
        const detachBtn = this.node.querySelector('.jp-DataingWidget-detach');
        if (detachBtn) {
            detachBtn.addEventListener('click', () => this.detach());
        }
    }
    /**
     * Render timeline events
     */
    _renderTimeline() {
        const timelineEl = this.node.querySelector('#dataing-timeline');
        if (!timelineEl)
            return;
        const eventColors = {
            run_started: '#3b82f6',
            run_progress: '#8b5cf6',
            run_evidence: '#10b981',
            run_completed: '#10b981',
            run_failed: '#ef4444',
            run_heartbeat: '#6b7280'
        };
        const eventIcons = {
            run_started: '\uD83D\uDE80',
            run_progress: '\u23F3',
            run_evidence: '\uD83D\uDCCB',
            run_completed: '\u2705',
            run_failed: '\u274C',
            run_heartbeat: '\uD83D\uDC93' // heartbeat
        };
        timelineEl.innerHTML = this._state.timeline
            .map((evt) => `
        <div class="jp-DataingWidget-event" style="border-left-color: ${eventColors[evt.event] || '#6b7280'};">
          <span class="jp-DataingWidget-event-icon">${eventIcons[evt.event] || '\u2022'}</span>
          <span class="jp-DataingWidget-event-type">${evt.event}</span>
          <span class="jp-DataingWidget-event-seq">#${evt.seq}</span>
        </div>
      `)
            .join('');
    }
    /**
     * Dispose of the widget
     */
    dispose() {
        this.stopStream();
        super.dispose();
    }
}


/***/ }

}]);
//# sourceMappingURL=lib_index_js.c035019edfa20b0f5224.js.map