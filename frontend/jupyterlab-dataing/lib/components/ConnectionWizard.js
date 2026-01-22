/**
 * Connection Wizard - Multi-step wizard for configuring Dataing backend connection.
 */
import * as React from 'react';
import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';
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
    return (React.createElement("div", { className: "jp-ConnectionWizard-step" },
        React.createElement("h4", null, "Step 1: Backend URL"),
        React.createElement("p", { className: "jp-ConnectionWizard-description" }, "Enter the URL of your Dataing backend server."),
        React.createElement("div", { className: "jp-ConnectionWizard-field" },
            React.createElement("label", { htmlFor: "backend-url" }, "Backend URL"),
            React.createElement("input", { id: "backend-url", type: "url", value: backendUrl, onChange: e => onChange(e.target.value), placeholder: "http://localhost:8000", className: "jp-ConnectionWizard-input", autoFocus: true })),
        recentUrls.length > 0 && (React.createElement("div", { className: "jp-ConnectionWizard-recent" },
            React.createElement("label", null, "Recent URLs"),
            React.createElement("div", { className: "jp-ConnectionWizard-recent-list" }, recentUrls.map(url => (React.createElement("button", { key: url, type: "button", className: "jp-ConnectionWizard-recent-item", onClick: () => onChange(url) }, url)))))),
        error && React.createElement("div", { className: "jp-ConnectionWizard-error" }, error)));
}
/**
 * Auth Step Component
 */
function AuthStep({ credentialMode, apiKey, sessionOnly, keychainAvailable, onApiKeyChange, onSessionOnlyChange, error }) {
    return (React.createElement("div", { className: "jp-ConnectionWizard-step" },
        React.createElement("h4", null, "Step 2: Authentication"),
        React.createElement("div", { className: "jp-ConnectionWizard-mode" },
            React.createElement("span", { className: "jp-ConnectionWizard-mode-label" }, "Storage mode:"),
            React.createElement("span", { className: "jp-ConnectionWizard-mode-value" }, formatCredentialMode(credentialMode))),
        React.createElement("p", { className: "jp-ConnectionWizard-description" },
            credentialMode === 'keychain' &&
                'Your API key will be stored securely in your OS keychain.',
            credentialMode === 'env_var' &&
                'API key loaded from DATAING_API_KEY environment variable.',
            credentialMode === 'session' &&
                'API key will only be stored for this session.'),
        React.createElement("div", { className: "jp-ConnectionWizard-field" },
            React.createElement("label", { htmlFor: "api-key" }, "API Key"),
            React.createElement("input", { id: "api-key", type: "password", value: apiKey, onChange: e => onApiKeyChange(e.target.value), placeholder: "Enter your Dataing API key", className: "jp-ConnectionWizard-input", autoComplete: "off" })),
        keychainAvailable && credentialMode === 'keychain' && (React.createElement("div", { className: "jp-ConnectionWizard-checkbox" },
            React.createElement("label", null,
                React.createElement("input", { type: "checkbox", checked: sessionOnly, onChange: e => onSessionOnlyChange(e.target.checked) }),
                "Don't store (session only)"))),
        error && React.createElement("div", { className: "jp-ConnectionWizard-error" }, error)));
}
/**
 * Test Step Component
 */
function TestStep({ testing, testResult, onTest, error }) {
    return (React.createElement("div", { className: "jp-ConnectionWizard-step" },
        React.createElement("h4", null, "Step 3: Test Connection"),
        !testResult && !testing && (React.createElement("div", null,
            React.createElement("p", { className: "jp-ConnectionWizard-description" }, "Click the button below to test your connection."),
            React.createElement("button", { type: "button", className: "jp-ConnectionWizard-button jp-ConnectionWizard-button-primary", onClick: onTest }, "Test Connection"))),
        testing && (React.createElement("div", { className: "jp-ConnectionWizard-testing" },
            React.createElement("span", { className: "jp-ConnectionWizard-spinner" }),
            React.createElement("span", null, "Testing connection..."))),
        testResult && !testing && (React.createElement("div", { className: `jp-ConnectionWizard-result ${testResult.success
                ? 'jp-ConnectionWizard-result-success'
                : 'jp-ConnectionWizard-result-error'}` }, testResult.success ? (React.createElement("span", null, "Connection successful!")) : (React.createElement("div", null,
            React.createElement("strong", null, "Connection failed"),
            React.createElement("p", null, testResult.error || 'Unknown error'),
            React.createElement("button", { type: "button", className: "jp-ConnectionWizard-button", onClick: onTest }, "Retry"))))),
        error && React.createElement("div", { className: "jp-ConnectionWizard-error" }, error)));
}
/**
 * Confirm Step Component
 */
function ConfirmStep({ backendUrl, credentialMode, saving, onSave, error }) {
    return (React.createElement("div", { className: "jp-ConnectionWizard-step" },
        React.createElement("h4", null, "Step 4: Save Configuration"),
        React.createElement("div", { className: "jp-ConnectionWizard-summary" },
            React.createElement("div", { className: "jp-ConnectionWizard-summary-row" },
                React.createElement("span", { className: "jp-ConnectionWizard-summary-label" }, "Backend URL:"),
                React.createElement("span", { className: "jp-ConnectionWizard-summary-value" }, backendUrl)),
            React.createElement("div", { className: "jp-ConnectionWizard-summary-row" },
                React.createElement("span", { className: "jp-ConnectionWizard-summary-label" }, "Credential Storage:"),
                React.createElement("span", { className: "jp-ConnectionWizard-summary-value" }, formatCredentialMode(credentialMode)))),
        React.createElement("button", { type: "button", className: "jp-ConnectionWizard-button jp-ConnectionWizard-button-primary", onClick: onSave, disabled: saving }, saving ? 'Saving...' : 'Save & Connect'),
        error && React.createElement("div", { className: "jp-ConnectionWizard-error" }, error)));
}
/**
 * Main Connection Wizard Component
 */
export function ConnectionWizard({ initialUrl = 'http://localhost:8000', recentUrls = [], serverBaseUrl, onConnect, onCancel }) {
    const [state, setState] = React.useState({
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
    const serverSettings = React.useMemo(() => {
        return serverBaseUrl
            ? ServerConnection.makeSettings({ baseUrl: serverBaseUrl })
            : ServerConnection.makeSettings();
    }, [serverBaseUrl]);
    const makeServerRequest = async (path, init) => {
        const url = URLExt.join(serverSettings.baseUrl, path);
        return ServerConnection.makeRequest(url, init, serverSettings);
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
    React.useEffect(() => {
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
    return (React.createElement("div", { className: "jp-ConnectionWizard" },
        React.createElement("div", { className: "jp-ConnectionWizard-header" },
            React.createElement("h3", null, "Connect to Dataing"),
            React.createElement("button", { type: "button", className: "jp-ConnectionWizard-close", onClick: onCancel, "aria-label": "Cancel" }, "\u00D7")),
        React.createElement("div", { className: "jp-ConnectionWizard-progress" }, [1, 2, 3, 4].map(step => (React.createElement("div", { key: step, className: `jp-ConnectionWizard-progress-step ${state.step === step
                ? 'jp-ConnectionWizard-progress-step-active'
                : state.step > step
                    ? 'jp-ConnectionWizard-progress-step-complete'
                    : ''}` }, step)))),
        React.createElement("div", { className: "jp-ConnectionWizard-content" },
            state.step === 1 && (React.createElement(UrlStep, { backendUrl: state.backendUrl, recentUrls: recentUrls, onChange: url => setState(s => ({ ...s, backendUrl: url })), error: state.error })),
            state.step === 2 && (React.createElement(AuthStep, { credentialMode: state.credentialMode, apiKey: state.apiKey, sessionOnly: state.sessionOnly, keychainAvailable: state.credentialMode === 'keychain', onApiKeyChange: key => setState(s => ({ ...s, apiKey: key })), onSessionOnlyChange: value => setState(s => ({ ...s, sessionOnly: value })), error: state.error })),
            state.step === 3 && (React.createElement(TestStep, { testing: state.testing, testResult: state.testResult, onTest: testConnection, error: state.error })),
            state.step === 4 && (React.createElement(ConfirmStep, { backendUrl: state.backendUrl, credentialMode: state.sessionOnly ? 'session' : state.credentialMode, saving: state.saving, onSave: saveCredentials, error: state.error }))),
        React.createElement("div", { className: "jp-ConnectionWizard-footer" },
            state.step > 1 && (React.createElement("button", { type: "button", className: "jp-ConnectionWizard-button", onClick: () => goToStep(state.step - 1) }, "Back")),
            React.createElement("div", { className: "jp-ConnectionWizard-footer-spacer" }),
            state.step < 4 && (React.createElement("button", { type: "button", className: "jp-ConnectionWizard-button jp-ConnectionWizard-button-primary", onClick: () => goToStep(state.step + 1), disabled: !canProceed() }, "Next")))));
}
//# sourceMappingURL=ConnectionWizard.js.map
