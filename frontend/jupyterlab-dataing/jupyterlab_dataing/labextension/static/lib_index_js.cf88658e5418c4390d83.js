"use strict";
(self["webpackChunk_dataing_jupyterlab_dataing"] = self["webpackChunk_dataing_jupyterlab_dataing"] || []).push([["lib_index_js"],{

/***/ "./lib/components/ConnectionWizard.js"
/*!********************************************!*\
  !*** ./lib/components/ConnectionWizard.js ***!
  \********************************************/
(__unused_webpack_module, __webpack_exports__, __webpack_require__) {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   ConnectionWizard: () => (/* binding */ ConnectionWizard)
/* harmony export */ });
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! react */ "webpack/sharing/consume/default/react");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @jupyterlab/coreutils */ "webpack/sharing/consume/default/@jupyterlab/coreutils");
/* harmony import */ var _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _jupyterlab_services__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @jupyterlab/services */ "webpack/sharing/consume/default/@jupyterlab/services");
/* harmony import */ var _jupyterlab_services__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_services__WEBPACK_IMPORTED_MODULE_2__);
/**
 * Connection Wizard - Multi-step wizard for configuring Dataing backend connection.
 */



/**
 * Format credential mode for display
 */
function formatCredentialMode(mode) {
    switch (mode) {
        case 'keychain':
            return 'OS Keychain';
        case 'env_var':
            return 'Environment Variable';
        case 'session':
            return 'Session Only';
        default:
            return mode;
    }
}
/**
 * URL Step Component
 */
function UrlStep({ backendUrl, recentUrls, onChange, error }) {
    return (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-step" },
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("h4", null, "Step 1: Backend URL"),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("p", { className: "jp-ConnectionWizard-description" }, "Enter the URL of your Dataing backend server."),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-field" },
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("label", { htmlFor: "backend-url" }, "Backend URL"),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("input", { id: "backend-url", type: "url", value: backendUrl, onChange: e => onChange(e.target.value), placeholder: "http://localhost:8000", className: "jp-ConnectionWizard-input", autoFocus: true })),
        recentUrls.length > 0 && (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-recent" },
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("label", null, "Recent URLs"),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-recent-list" }, recentUrls.map(url => (react__WEBPACK_IMPORTED_MODULE_0__.createElement("button", { key: url, type: "button", className: "jp-ConnectionWizard-recent-item", onClick: () => onChange(url) }, url)))))),
        error && react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-error" }, error)));
}
/**
 * Auth Step Component
 */
function AuthStep({ credentialMode, apiKey, sessionOnly, keychainAvailable, onApiKeyChange, onSessionOnlyChange, error }) {
    return (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-step" },
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("h4", null, "Step 2: Authentication"),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-mode" },
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("span", { className: "jp-ConnectionWizard-mode-label" }, "Storage mode:"),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("span", { className: "jp-ConnectionWizard-mode-value" }, formatCredentialMode(credentialMode))),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("p", { className: "jp-ConnectionWizard-description" },
            credentialMode === 'keychain' &&
                'Your API key will be stored securely in your OS keychain.',
            credentialMode === 'env_var' &&
                'API key loaded from DATAING_API_KEY environment variable.',
            credentialMode === 'session' &&
                'API key will only be stored for this session.'),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-field" },
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("label", { htmlFor: "api-key" }, "API Key"),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("input", { id: "api-key", type: "password", value: apiKey, onChange: e => onApiKeyChange(e.target.value), placeholder: "Enter your Dataing API key", className: "jp-ConnectionWizard-input", autoComplete: "off" })),
        keychainAvailable && credentialMode === 'keychain' && (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-checkbox" },
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("label", null,
                react__WEBPACK_IMPORTED_MODULE_0__.createElement("input", { type: "checkbox", checked: sessionOnly, onChange: e => onSessionOnlyChange(e.target.checked) }),
                "Don't store (session only)"))),
        error && react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-error" }, error)));
}
/**
 * Test Step Component
 */
function TestStep({ testing, testResult, onTest, error }) {
    return (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-step" },
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("h4", null, "Step 3: Test Connection"),
        !testResult && !testing && (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", null,
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("p", { className: "jp-ConnectionWizard-description" }, "Click the button below to test your connection."),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("button", { type: "button", className: "jp-ConnectionWizard-button jp-ConnectionWizard-button-primary", onClick: onTest }, "Test Connection"))),
        testing && (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-testing" },
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("span", { className: "jp-ConnectionWizard-spinner" }),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("span", null, "Testing connection..."))),
        testResult && !testing && (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: `jp-ConnectionWizard-result ${testResult.success
                ? 'jp-ConnectionWizard-result-success'
                : 'jp-ConnectionWizard-result-error'}` }, testResult.success ? (react__WEBPACK_IMPORTED_MODULE_0__.createElement("span", null, "Connection successful!")) : (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", null,
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("strong", null, "Connection failed"),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("p", null, testResult.error || 'Unknown error'),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("button", { type: "button", className: "jp-ConnectionWizard-button", onClick: onTest }, "Retry"))))),
        error && react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-error" }, error)));
}
/**
 * Confirm Step Component
 */
function ConfirmStep({ backendUrl, credentialMode, saving, onSave, error }) {
    return (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-step" },
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("h4", null, "Step 4: Save Configuration"),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-summary" },
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-summary-row" },
                react__WEBPACK_IMPORTED_MODULE_0__.createElement("span", { className: "jp-ConnectionWizard-summary-label" }, "Backend URL:"),
                react__WEBPACK_IMPORTED_MODULE_0__.createElement("span", { className: "jp-ConnectionWizard-summary-value" }, backendUrl)),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-summary-row" },
                react__WEBPACK_IMPORTED_MODULE_0__.createElement("span", { className: "jp-ConnectionWizard-summary-label" }, "Credential Storage:"),
                react__WEBPACK_IMPORTED_MODULE_0__.createElement("span", { className: "jp-ConnectionWizard-summary-value" }, formatCredentialMode(credentialMode)))),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("button", { type: "button", className: "jp-ConnectionWizard-button jp-ConnectionWizard-button-primary", onClick: onSave, disabled: saving }, saving ? 'Saving...' : 'Save & Connect'),
        error && react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-error" }, error)));
}
/**
 * Main Connection Wizard Component
 */
function ConnectionWizard({ initialUrl = 'http://localhost:8000', recentUrls = [], serverBaseUrl, onConnect, onCancel }) {
    const [state, setState] = react__WEBPACK_IMPORTED_MODULE_0__.useState({
        step: 1,
        backendUrl: initialUrl,
        apiKey: '',
        credentialMode: 'session',
        sessionOnly: false,
        testResult: null,
        testing: false,
        saving: false,
        error: null
    });
    const serverSettings = react__WEBPACK_IMPORTED_MODULE_0__.useMemo(() => {
        return serverBaseUrl
            ? _jupyterlab_services__WEBPACK_IMPORTED_MODULE_2__.ServerConnection.makeSettings({ baseUrl: serverBaseUrl })
            : _jupyterlab_services__WEBPACK_IMPORTED_MODULE_2__.ServerConnection.makeSettings();
    }, [serverBaseUrl]);
    const makeServerRequest = async (path, init) => {
        const url = _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_1__.URLExt.join(serverSettings.baseUrl, path);
        return _jupyterlab_services__WEBPACK_IMPORTED_MODULE_2__.ServerConnection.makeRequest(url, init, serverSettings);
    };
    const getErrorMessage = async (response) => {
        try {
            const data = await response.json();
            if (data && typeof data.error === 'string' && data.error.length > 0) {
                return data.error;
            }
        }
        catch {
            // Ignore JSON parse errors.
        }
        return response.statusText || `Request failed (${response.status})`;
    };
    // Fetch credential mode when URL changes
    react__WEBPACK_IMPORTED_MODULE_0__.useEffect(() => {
        if (state.step === 2 && state.backendUrl) {
            fetchCredentialMode();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [state.step, state.backendUrl]);
    const fetchCredentialMode = async () => {
        try {
            const response = await makeServerRequest('dataing/credentials', {
                method: 'GET'
            });
            if (response.ok) {
                const data = await response.json();
                setState(s => ({
                    ...s,
                    credentialMode: data.mode || 'session',
                    // If env_var mode, API key may already be set
                    apiKey: data.has_api_key && data.mode === 'env_var' ? '••••••••' : s.apiKey
                }));
            }
        }
        catch (error) {
            console.warn('Failed to fetch credential mode:', error);
        }
    };
    const testConnection = async () => {
        setState(s => ({ ...s, testing: true, testResult: null, error: null }));
        try {
            const response = await makeServerRequest('dataing/connection/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    base_url: state.backendUrl,
                    api_key: state.apiKey
                })
            });
            if (!response.ok) {
                const errorMessage = await getErrorMessage(response);
                setState(s => ({
                    ...s,
                    testing: false,
                    testResult: {
                        success: false,
                        error: errorMessage
                    }
                }));
                return;
            }
            const data = await response.json();
            setState(s => ({
                ...s,
                testing: false,
                testResult: {
                    success: data.success,
                    error: data.error
                }
            }));
        }
        catch (error) {
            setState(s => ({
                ...s,
                testing: false,
                testResult: {
                    success: false,
                    error: error instanceof Error ? error.message : 'Network error'
                }
            }));
        }
    };
    const saveCredentials = async () => {
        setState(s => ({ ...s, saving: true, error: null }));
        try {
            const effectiveMode = state.sessionOnly ? 'session' : state.credentialMode;
            const response = await makeServerRequest('dataing/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    base_url: state.backendUrl,
                    api_key: state.apiKey,
                    mode: effectiveMode
                })
            });
            if (!response.ok) {
                const errorMessage = await getErrorMessage(response);
                throw new Error(errorMessage || 'Failed to save credentials');
            }
            setState(s => ({ ...s, saving: false }));
            onConnect(state.backendUrl, effectiveMode);
        }
        catch (error) {
            setState(s => ({
                ...s,
                saving: false,
                error: error instanceof Error ? error.message : 'Failed to save'
            }));
        }
    };
    const goToStep = (step) => {
        setState(s => ({ ...s, step, error: null }));
    };
    const canProceed = () => {
        switch (state.step) {
            case 1:
                return state.backendUrl.trim().length > 0;
            case 2:
                return state.apiKey.trim().length > 0;
            case 3:
                return state.testResult?.success === true;
            default:
                return true;
        }
    };
    return (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard" },
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-header" },
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("h3", null, "Connect to Dataing"),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("button", { type: "button", className: "jp-ConnectionWizard-close", onClick: onCancel, "aria-label": "Cancel" }, "\u00D7")),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-progress" }, [1, 2, 3, 4].map(step => (react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { key: step, className: `jp-ConnectionWizard-progress-step ${state.step === step
                ? 'jp-ConnectionWizard-progress-step-active'
                : state.step > step
                    ? 'jp-ConnectionWizard-progress-step-complete'
                    : ''}` }, step)))),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-content" },
            state.step === 1 && (react__WEBPACK_IMPORTED_MODULE_0__.createElement(UrlStep, { backendUrl: state.backendUrl, recentUrls: recentUrls, onChange: url => setState(s => ({ ...s, backendUrl: url })), error: state.error })),
            state.step === 2 && (react__WEBPACK_IMPORTED_MODULE_0__.createElement(AuthStep, { credentialMode: state.credentialMode, apiKey: state.apiKey, sessionOnly: state.sessionOnly, keychainAvailable: state.credentialMode === 'keychain', onApiKeyChange: key => setState(s => ({ ...s, apiKey: key })), onSessionOnlyChange: value => setState(s => ({ ...s, sessionOnly: value })), error: state.error })),
            state.step === 3 && (react__WEBPACK_IMPORTED_MODULE_0__.createElement(TestStep, { testing: state.testing, testResult: state.testResult, onTest: testConnection, error: state.error })),
            state.step === 4 && (react__WEBPACK_IMPORTED_MODULE_0__.createElement(ConfirmStep, { backendUrl: state.backendUrl, credentialMode: state.sessionOnly ? 'session' : state.credentialMode, saving: state.saving, onSave: saveCredentials, error: state.error }))),
        react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-footer" },
            state.step > 1 && (react__WEBPACK_IMPORTED_MODULE_0__.createElement("button", { type: "button", className: "jp-ConnectionWizard-button", onClick: () => goToStep(state.step - 1) }, "Back")),
            react__WEBPACK_IMPORTED_MODULE_0__.createElement("div", { className: "jp-ConnectionWizard-footer-spacer" }),
            state.step < 4 && (react__WEBPACK_IMPORTED_MODULE_0__.createElement("button", { type: "button", className: "jp-ConnectionWizard-button jp-ConnectionWizard-button-primary", onClick: () => goToStep(state.step + 1), disabled: !canProceed() }, "Next")))));
}


/***/ },

/***/ "./lib/connectionWizard.js"
/*!*********************************!*\
  !*** ./lib/connectionWizard.js ***!
  \*********************************/
(__unused_webpack_module, __webpack_exports__, __webpack_require__) {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   ConnectionWizardWidget: () => (/* binding */ ConnectionWizardWidget),
/* harmony export */   createConnectionWizardWidget: () => (/* binding */ createConnectionWizardWidget)
/* harmony export */ });
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! react */ "webpack/sharing/consume/default/react");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @jupyterlab/apputils */ "webpack/sharing/consume/default/@jupyterlab/apputils");
/* harmony import */ var _jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _components_ConnectionWizard__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ./components/ConnectionWizard */ "./lib/components/ConnectionWizard.js");
/**
 * Connection Wizard Lumino Widget wrapper.
 *
 * Wraps the React ConnectionWizard component in a Lumino ReactWidget
 * for integration with JupyterLab's panel system.
 */



/**
 * ConnectionWizardWidget - Lumino wrapper for ConnectionWizard React component.
 */
class ConnectionWizardWidget extends _jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_1__.ReactWidget {
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
        return react__WEBPACK_IMPORTED_MODULE_0__.createElement(_components_ConnectionWizard__WEBPACK_IMPORTED_MODULE_2__.ConnectionWizard, {
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
function createConnectionWizardWidget(options) {
    return new ConnectionWizardWidget(options);
}


/***/ },

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
/* harmony import */ var _jupyterlab_notebook__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! @jupyterlab/notebook */ "webpack/sharing/consume/default/@jupyterlab/notebook");
/* harmony import */ var _jupyterlab_notebook__WEBPACK_IMPORTED_MODULE_5___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_notebook__WEBPACK_IMPORTED_MODULE_5__);
/* harmony import */ var _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! @jupyterlab/coreutils */ "webpack/sharing/consume/default/@jupyterlab/coreutils");
/* harmony import */ var _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_6___default = /*#__PURE__*/__webpack_require__.n(_jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_6__);
/* harmony import */ var _lumino_coreutils__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! @lumino/coreutils */ "webpack/sharing/consume/default/@lumino/coreutils");
/* harmony import */ var _lumino_coreutils__WEBPACK_IMPORTED_MODULE_7___default = /*#__PURE__*/__webpack_require__.n(_lumino_coreutils__WEBPACK_IMPORTED_MODULE_7__);
/* harmony import */ var _statusbar__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(/*! ./statusbar */ "./lib/statusbar.js");
/* harmony import */ var _widget__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(/*! ./widget */ "./lib/widget.js");
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
    showStatusBar: true,
    recentUrls: [],
    workspaceId: ''
};
const MIN_CONNECTION_CHECK_INTERVAL = 5;
const MAX_CONNECTION_CHECK_INTERVAL = 300;
/**
 * Generate a UUID v4 for workspace identification
 */
function generateUUID() {
    // Use crypto.randomUUID if available, otherwise fallback
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    // Fallback for older browsers
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}
/**
 * Maximum number of recent URLs to store
 */
const MAX_RECENT_URLS = 10;
function normalizeBackendUrl(url) {
    return url.replace(/\/+$/, '');
}
/**
 * Check connection via server extension proxy using ServerConnection
 */
async function checkConnection(serverSettings, abortSignal) {
    try {
        // Check server extension handshake using ServerConnection
        const handshakeUrl = _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_6__.URLExt.join(serverSettings.baseUrl, 'dataing/handshake');
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
        const proxyUrl = _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_6__.URLExt.join(serverSettings.baseUrl, 'dataing/proxy/health');
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
    optional: [_jupyterlab_settingregistry__WEBPACK_IMPORTED_MODULE_1__.ISettingRegistry, _jupyterlab_statusbar__WEBPACK_IMPORTED_MODULE_2__.IStatusBar, _jupyterlab_apputils__WEBPACK_IMPORTED_MODULE_3__.ICommandPalette, _jupyterlab_application__WEBPACK_IMPORTED_MODULE_0__.ILayoutRestorer, _jupyterlab_notebook__WEBPACK_IMPORTED_MODULE_5__.INotebookTracker],
    activate: async (app, settingRegistry, statusBar, palette, restorer, notebookTracker) => {
        if (typeof window !== 'undefined') {
            const globalWindow = window;
            if (globalWindow.__dataingJupyterlabActivated) {
                console.warn('Dataing: extension already activated, skipping duplicate instance.');
                return;
            }
            globalWindow.__dataingJupyterlabActivated = true;
        }
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
        let lastCheckedBackendUrl = null;
        let lastConnectionCheckCallMs = 0;
        const globalCheckState = (() => {
            if (typeof window === 'undefined') {
                return { inFlight: false, lastCheckMs: 0 };
            }
            const globalWindow = window;
            if (!globalWindow.__dataingGlobalCheckState) {
                globalWindow.__dataingGlobalCheckState = { inFlight: false, lastCheckMs: 0 };
            }
            return globalWindow.__dataingGlobalCheckState;
        })();
        // Callback to add URL to recent list (set when settings loaded)
        let onConnectionSuccess = null;
        // Function to update backend URL (set when settings loaded, used by wizard)
        let updateBackendUrlFn = null;
        // Function to get recent URLs (set when settings loaded, used by wizard)
        let getRecentUrlsFn = null;
        // Function to update connection state
        const updateConnectionState = async (force = false, source = 'unknown') => {
            const now = Date.now();
            const normalizedCurrentUrl = normalizeBackendUrl(settings.backendUrl);
            const normalizedLastCheckedUrl = lastCheckedBackendUrl
                ? normalizeBackendUrl(lastCheckedBackendUrl)
                : null;
            const hasSameUrl = normalizedLastCheckedUrl !== null &&
                normalizedLastCheckedUrl === normalizedCurrentUrl;
            const intervalSeconds = Number.isFinite(settings.connectionCheckInterval)
                ? settings.connectionCheckInterval
                : MIN_CONNECTION_CHECK_INTERVAL;
            const minIntervalMs = Math.max(intervalSeconds * 1000, MIN_CONNECTION_CHECK_INTERVAL * 1000);
            const callDeltaMs = lastConnectionCheckCallMs ? now - lastConnectionCheckCallMs : null;
            lastConnectionCheckCallMs = now;
            if (callDeltaMs !== null && callDeltaMs < 1000) {
                console.warn('Dataing: rapid connection check call', {
                    source,
                    callDeltaMs,
                    force,
                    checkInFlight,
                    lastCheck: state.lastCheck ? state.lastCheck.toISOString() : null,
                    minIntervalMs
                });
            }
            if (globalCheckState.lastCheckMs &&
                now - globalCheckState.lastCheckMs < minIntervalMs) {
                return;
            }
            if (globalCheckState.inFlight) {
                return;
            }
            if ((!force || hasSameUrl) &&
                state.lastCheck &&
                now - state.lastCheck.getTime() < minIntervalMs) {
                return;
            }
            // Guard concurrent checks
            if (checkInFlight) {
                return;
            }
            checkInFlight = true;
            globalCheckState.inFlight = true;
            globalCheckState.lastCheckMs = now;
            const previousState = state.connectionState; // Track for state transition detection
            state.connectionState = 'checking';
            state.lastCheck = new Date();
            lastCheckedBackendUrl = settings.backendUrl;
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
                const resolvedBackendUrl = result.backendUrl || settings.backendUrl;
                state.backendUrl = normalizeBackendUrl(resolvedBackendUrl);
                if (result.backendOk) {
                    state.connectionState = 'connected';
                    state.errorMessage = null;
                    // Add to recent URLs only on state transition TO connected (not every periodic check)
                    if (previousState !== 'connected' && onConnectionSuccess && state.backendUrl) {
                        try {
                            await onConnectionSuccess(state.backendUrl);
                        }
                        catch (error) {
                            console.warn('Failed to save recent Dataing URL:', error);
                        }
                    }
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
                globalCheckState.inFlight = false;
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
            const intervalSeconds = Number.isFinite(settings.connectionCheckInterval)
                ? settings.connectionCheckInterval
                : MIN_CONNECTION_CHECK_INTERVAL;
            const intervalMs = Math.max(intervalSeconds * 1000, MIN_CONNECTION_CHECK_INTERVAL * 1000);
            checkTimerId = setTimeout(async () => {
                await updateConnectionState(false, 'timer');
                scheduleNextCheck();
            }, intervalMs);
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
                        const normalizedUrl = normalizeBackendUrl(backendUrl);
                        settings.backendUrl = normalizedUrl;
                        state.backendUrl = normalizedUrl;
                    }
                    const autoConnect = settingsObj.get('autoConnect').composite;
                    if (typeof autoConnect === 'boolean') {
                        settings.autoConnect = autoConnect;
                    }
                    const checkInterval = settingsObj.get('connectionCheckInterval').composite;
                    if (typeof checkInterval === 'number' && Number.isFinite(checkInterval)) {
                        const clampedInterval = Math.min(Math.max(checkInterval, MIN_CONNECTION_CHECK_INTERVAL), MAX_CONNECTION_CHECK_INTERVAL);
                        settings.connectionCheckInterval = clampedInterval;
                    }
                    const showStatusBar = settingsObj.get('showStatusBar').composite;
                    if (typeof showStatusBar === 'boolean') {
                        settings.showStatusBar = showStatusBar;
                    }
                    const recentUrls = settingsObj.get('recentUrls').composite;
                    if (Array.isArray(recentUrls)) {
                        settings.recentUrls = recentUrls;
                    }
                    const workspaceId = settingsObj.get('workspaceId').composite;
                    if (typeof workspaceId === 'string' && workspaceId) {
                        settings.workspaceId = workspaceId;
                    }
                };
                const internalSaveKeys = new Set(['recentUrls', 'workspaceId']);
                const pendingSettingWrites = new Map();
                let pendingInternalSaveCount = 0;
                // Function to save a single setting (tracks key to prevent re-check loop)
                const saveSetting = async (key, value) => {
                    const existingValue = settingsObj.get(key).composite;
                    if (existingValue !== undefined && _lumino_coreutils__WEBPACK_IMPORTED_MODULE_7__.JSONExt.deepEqual(existingValue, value)) {
                        return;
                    }
                    const pendingValue = pendingSettingWrites.get(key);
                    if (pendingValue !== undefined && _lumino_coreutils__WEBPACK_IMPORTED_MODULE_7__.JSONExt.deepEqual(pendingValue, value)) {
                        return;
                    }
                    pendingSettingWrites.set(key, value);
                    const isInternalKey = internalSaveKeys.has(key);
                    if (isInternalKey) {
                        pendingInternalSaveCount += 1;
                    }
                    try {
                        await settingsObj.set(key, value);
                    }
                    catch (error) {
                        if (isInternalKey) {
                            pendingInternalSaveCount = Math.max(0, pendingInternalSaveCount - 1);
                        }
                        console.warn(`Failed to save Dataing setting '${key}':`, error);
                    }
                    finally {
                        pendingSettingWrites.delete(key);
                    }
                };
                // Function to update backendUrl - expose via outer variable for wizard
                updateBackendUrlFn = async (newUrl) => {
                    const normalizedUrl = normalizeBackendUrl(newUrl);
                    if (!normalizedUrl) {
                        return;
                    }
                    await saveSetting('backendUrl', normalizedUrl);
                    settings.backendUrl = normalizedUrl;
                    state.backendUrl = normalizedUrl;
                };
                // Function to get recent URLs - expose via outer variable for wizard
                getRecentUrlsFn = () => [...settings.recentUrls];
                // Function to add URL to recent URLs list
                const addToRecentUrls = async (url) => {
                    const normalizedUrl = normalizeBackendUrl(url);
                    const filtered = settings.recentUrls.filter(u => u !== normalizedUrl);
                    const updated = [normalizedUrl, ...filtered].slice(0, MAX_RECENT_URLS);
                    const isSame = updated.length === settings.recentUrls.length &&
                        updated.every((value, index) => value === settings.recentUrls[index]);
                    if (isSame) {
                        return;
                    }
                    await saveSetting('recentUrls', updated);
                    settings.recentUrls = updated;
                };
                // Wire up callback for connection success
                onConnectionSuccess = addToRecentUrls;
                // Initial load
                loadAllSettings();
                // Generate workspaceId on first launch if not set
                if (!settings.workspaceId) {
                    const newWorkspaceId = generateUUID();
                    settings.workspaceId = newWorkspaceId;
                    void saveSetting('workspaceId', newWorkspaceId);
                    console.log('Dataing: Generated new workspace ID:', newWorkspaceId);
                }
                else {
                    console.log('Dataing: Using existing workspace ID:', settings.workspaceId);
                }
                // Watch for settings changes - reload all and reschedule
                settingsObj.changed.connect(() => {
                    // Skip connection re-check if this is an internal save (e.g., recentUrls, workspaceId)
                    const isInternalSave = pendingInternalSaveCount > 0;
                    if (isInternalSave) {
                        pendingInternalSaveCount = Math.max(0, pendingInternalSaveCount - 1);
                    }
                    const oldAutoConnect = settings.autoConnect;
                    const oldInterval = settings.connectionCheckInterval;
                    const oldBackendUrl = settings.backendUrl;
                    loadAllSettings();
                    // If autoConnect changed or interval changed, reschedule
                    if (oldAutoConnect !== settings.autoConnect || oldInterval !== settings.connectionCheckInterval) {
                        scheduleNextCheck(); // Will clear old timer and respect new settings
                    }
                    // Only re-check connection if backendUrl changed by user (not internal save)
                    const normalizedOldBackendUrl = normalizeBackendUrl(oldBackendUrl);
                    const normalizedNewBackendUrl = normalizeBackendUrl(settings.backendUrl);
                    if (!isInternalSave && normalizedOldBackendUrl !== normalizedNewBackendUrl) {
                        void updateConnectionState(true, 'settings-changed');
                    }
                });
                console.log('Dataing settings loaded:', settings);
            }
            catch (error) {
                console.warn('Could not load Dataing settings:', error);
            }
        }
        // Add status bar widget if available and enabled
        if (statusBar && settings.showStatusBar) {
            statusBarWidget = new _statusbar__WEBPACK_IMPORTED_MODULE_8__.DataingStatusBar(state);
            statusBar.registerStatusItem(EXTENSION_ID, {
                item: statusBarWidget,
                align: 'right',
                rank: 100
            });
            console.log('Dataing status bar widget added');
        }
        // Create and add sidebar widget
        sidebarWidget = new _widget__WEBPACK_IMPORTED_MODULE_9__.DataingWidget();
        sidebarWidget.id = 'dataing-sidebar';
        sidebarWidget.title.iconClass = 'jp-DataingIcon';
        sidebarWidget.title.caption = 'Dataing';
        // Set server base URL for wizard API calls
        sidebarWidget.setServerBaseUrl(serverSettings.baseUrl);
        // Expose settings functions on widget for Connection Wizard to use
        if (updateBackendUrlFn) {
            sidebarWidget._updateBackendUrl = updateBackendUrlFn;
        }
        if (getRecentUrlsFn) {
            sidebarWidget._getRecentUrls = getRecentUrlsFn;
        }
        // Set workspace ID on widget
        sidebarWidget.setWorkspaceId(settings.workspaceId);
        // Track active kernel for workspace state
        let currentKernelId = null;
        // Function to update kernel tracking
        const updateActiveKernel = () => {
            if (!sidebarWidget) {
                return;
            }
            const notebookPanel = notebookTracker?.currentWidget ?? null;
            const kernel = notebookPanel?.sessionContext?.session?.kernel ?? null;
            const newKernelId = kernel?.id ?? null;
            if (newKernelId !== currentKernelId) {
                currentKernelId = newKernelId;
                sidebarWidget.setActiveKernel(newKernelId);
                console.log('Dataing: Active kernel changed:', newKernelId || '(none)');
            }
        };
        // Listen for notebook changes if tracker available
        if (notebookTracker) {
            // Track when current notebook changes
            notebookTracker.currentChanged.connect(() => {
                updateActiveKernel();
            });
            // Track when any notebook's kernel status changes
            notebookTracker.widgetAdded.connect((_tracker, panel) => {
                panel.sessionContext.statusChanged.connect(() => {
                    // Only update if this is the current notebook
                    if (panel === notebookTracker.currentWidget) {
                        updateActiveKernel();
                    }
                });
                // Track kernel changes (e.g., restart, shutdown)
                panel.sessionContext.kernelChanged.connect(() => {
                    if (panel === notebookTracker.currentWidget) {
                        updateActiveKernel();
                    }
                });
            });
            // Initial update
            updateActiveKernel();
        }
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
                const stateUrl = _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_6__.URLExt.join(serverSettings.baseUrl, STATE_ENDPOINT);
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
                const stateUrl = _jupyterlab_coreutils__WEBPACK_IMPORTED_MODULE_6__.URLExt.join(serverSettings.baseUrl, STATE_ENDPOINT);
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
            await updateConnectionState(false, 'initial');
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
/* harmony import */ var _connectionWizard__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ./connectionWizard */ "./lib/connectionWizard.js");
/**
 * DataingWidget - Main sidebar widget for Dataing integration.
 *
 * Provides:
 * - Connection status display
 * - Connection wizard for configuring backend
 * - Datasource attach UI
 * - SSE streaming for run events
 * - Timeline rendering
 */



/**
 * DataingWidget - Main sidebar widget
 */
class DataingWidget extends _lumino_widgets__WEBPACK_IMPORTED_MODULE_0__.Panel {
    /**
     * Construct a new DataingWidget
     */
    constructor() {
        super();
        this._eventSource = null;
        this._stateChanged = new _lumino_signaling__WEBPACK_IMPORTED_MODULE_1__.Signal(this);
        this._wizardWidget = null;
        this._serverBaseUrl = '';
        this.id = 'dataing-widget';
        this.title.label = 'Dataing';
        this.title.closable = true;
        this.addClass('jp-DataingWidget');
        this._state = {
            connectionState: 'disconnected',
            backendUrl: '',
            credentialMode: null,
            showWizard: false,
            attachedDatasource: null,
            currentRunId: null,
            timeline: [],
            errorMessage: null,
            workspaceId: null,
            kernelId: null
        };
        // Create content widget for main UI
        this._contentWidget = new _lumino_widgets__WEBPACK_IMPORTED_MODULE_0__.Widget();
        this._contentWidget.addClass('jp-DataingWidget-main');
        this.addWidget(this._contentWidget);
        this._render();
    }
    /**
     * Set the server base URL (used for wizard API calls)
     */
    setServerBaseUrl(url) {
        this._serverBaseUrl = url;
    }
    /**
     * Set the workspace ID (generated on first launch, persisted)
     */
    setWorkspaceId(workspaceId) {
        this._state.workspaceId = workspaceId;
    }
    /**
     * Set the active kernel ID (from current notebook)
     * Pass null when no notebook is active or no kernel is running
     */
    setActiveKernel(kernelId) {
        const changed = this._state.kernelId !== kernelId;
        this._state.kernelId = kernelId;
        if (changed) {
            this._render();
            this._stateChanged.emit(this._state);
        }
    }
    /**
     * Get current workspace context (workspace_id + kernel_id)
     */
    getWorkspaceContext() {
        return {
            workspaceId: this._state.workspaceId,
            kernelId: this._state.kernelId
        };
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
     * Show the connection wizard
     */
    showWizard() {
        if (this._wizardWidget) {
            return; // Already showing
        }
        this._state.showWizard = true;
        // Hide main content
        this._contentWidget.hide();
        // Create and show wizard
        this._wizardWidget = (0,_connectionWizard__WEBPACK_IMPORTED_MODULE_2__.createConnectionWizardWidget)({
            initialUrl: this._state.backendUrl || 'http://localhost:8000',
            recentUrls: this._getRecentUrls?.() || [],
            serverBaseUrl: this._serverBaseUrl,
            onConnect: this._handleWizardConnect.bind(this),
            onCancel: this._handleWizardCancel.bind(this)
        });
        this.addWidget(this._wizardWidget);
        this._stateChanged.emit(this._state);
    }
    /**
     * Hide the connection wizard
     */
    hideWizard() {
        if (!this._wizardWidget) {
            return;
        }
        this._state.showWizard = false;
        // Remove wizard
        this._wizardWidget.dispose();
        this._wizardWidget = null;
        // Show main content
        this._contentWidget.show();
        this._render();
        this._stateChanged.emit(this._state);
    }
    /**
     * Handle wizard connect callback
     */
    _handleWizardConnect(url, mode) {
        this._state.backendUrl = url;
        this._state.credentialMode = mode;
        // Persist URL to settings if function available
        if (this._updateBackendUrl) {
            void this._updateBackendUrl(url);
        }
        this.hideWizard();
    }
    /**
     * Handle wizard cancel callback
     */
    _handleWizardCancel() {
        this.hideWizard();
    }
    /**
     * Copy connection snippet to clipboard
     *
     * Fetches the snippet from the server to include attach commands
     * and proper credential mode comments.
     */
    async _copySnippet() {
        try {
            const response = await fetch(`${this._serverBaseUrl}dataing/snippet`, {
                credentials: 'same-origin'
            });
            if (response.ok) {
                const data = await response.json();
                const snippet = data.snippet;
                await navigator.clipboard.writeText(snippet);
                console.log('Copied to clipboard:', snippet);
            }
            else {
                // Fallback to simple snippet
                const fallback = `%dataing connect --base-url ${this._state.backendUrl}`;
                await navigator.clipboard.writeText(fallback);
                console.log('Copied fallback to clipboard:', fallback);
            }
        }
        catch (error) {
            // Fallback on error
            const fallback = `%dataing connect --base-url ${this._state.backendUrl}`;
            await navigator.clipboard.writeText(fallback);
            console.log('Copied fallback to clipboard:', fallback);
        }
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
     * Format credential mode for display
     */
    _formatCredentialMode(mode) {
        if (!mode)
            return 'Unknown';
        switch (mode) {
            case 'keychain':
                return 'OS Keychain';
            case 'env_var':
                return 'Environment Variable';
            case 'session':
                return 'Session Only';
            default:
                return mode;
        }
    }
    /**
     * Render the widget
     */
    _render() {
        const { connectionState, backendUrl, credentialMode, attachedDatasource, errorMessage, kernelId } = this._state;
        // Status badge color
        const statusColors = {
            connected: '#10b981',
            disconnected: '#6b7280',
            checking: '#f59e0b',
            error: '#ef4444'
        };
        const isConnected = connectionState === 'connected';
        const isDisconnected = connectionState === 'disconnected' || connectionState === 'error';
        const hasKernel = kernelId !== null;
        this._contentWidget.node.innerHTML = `
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

        ${isDisconnected
            ? `
          <div class="jp-DataingWidget-connect-section">
            <p>Not connected to Dataing backend.</p>
            <button class="jp-DataingWidget-connect-btn">Connect</button>
          </div>
        `
            : ''}

        ${isConnected
            ? `
          <div class="jp-DataingWidget-section">
            <label>Backend URL</label>
            <div class="jp-DataingWidget-value">${backendUrl || 'Not configured'}</div>
          </div>

          <div class="jp-DataingWidget-section">
            <label>Credential Storage</label>
            <div class="jp-DataingWidget-value">${this._formatCredentialMode(credentialMode)}</div>
          </div>

          <div class="jp-DataingWidget-actions">
            <button class="jp-DataingWidget-edit-btn">Edit Connection</button>
            <button class="jp-DataingWidget-copy-btn">Copy Snippet</button>
          </div>

          <div class="jp-DataingWidget-section">
            <label>Notebook Kernel</label>
            <div class="jp-DataingWidget-value">
              ${hasKernel ? '<span style="color: #10b981;">Active</span>' : '<span style="color: #6b7280;">Select a notebook to run investigations</span>'}
            </div>
          </div>

          <div class="jp-DataingWidget-section">
            <label>Attached Datasource</label>
            <div class="jp-DataingWidget-value">
              ${attachedDatasource || 'None'}
              ${attachedDatasource ? '<button class="jp-DataingWidget-detach">Detach</button>' : ''}
            </div>
          </div>
        `
            : ''}

        ${connectionState === 'checking'
            ? `
          <div class="jp-DataingWidget-checking">
            <span class="jp-DataingWidget-spinner"></span>
            <span>Checking connection...</span>
          </div>
        `
            : ''}

        ${errorMessage
            ? `
          <div class="jp-DataingWidget-error">
            ${errorMessage}
          </div>
        `
            : ''}

        <div class="jp-DataingWidget-timeline" id="dataing-timeline">
          <!-- Timeline events rendered here -->
        </div>
      </div>
    `;
        // Add event listeners
        const connectBtn = this._contentWidget.node.querySelector('.jp-DataingWidget-connect-btn');
        if (connectBtn) {
            connectBtn.addEventListener('click', () => this.showWizard());
        }
        const editBtn = this._contentWidget.node.querySelector('.jp-DataingWidget-edit-btn');
        if (editBtn) {
            editBtn.addEventListener('click', () => this.showWizard());
        }
        const copyBtn = this._contentWidget.node.querySelector('.jp-DataingWidget-copy-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => this._copySnippet());
        }
        const detachBtn = this._contentWidget.node.querySelector('.jp-DataingWidget-detach');
        if (detachBtn) {
            detachBtn.addEventListener('click', () => this.detach());
        }
    }
    /**
     * Render timeline events
     */
    _renderTimeline() {
        const timelineEl = this._contentWidget.node.querySelector('#dataing-timeline');
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
//# sourceMappingURL=lib_index_js.cf88658e5418c4390d83.js.map
