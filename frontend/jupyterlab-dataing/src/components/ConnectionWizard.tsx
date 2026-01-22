/**
 * Connection Wizard - Multi-step wizard for configuring Dataing backend connection.
 */

import * as React from 'react';

/**
 * Credential mode detected from server
 */
export type CredentialMode = 'keychain' | 'env_var' | 'session';

/**
 * Connection test result
 */
export interface ITestResult {
  success: boolean;
  error?: string;
}

/**
 * Wizard state
 */
interface IWizardState {
  step: number;
  backendUrl: string;
  apiKey: string;
  credentialMode: CredentialMode;
  sessionOnly: boolean;
  testResult: ITestResult | null;
  testing: boolean;
  saving: boolean;
  error: string | null;
}

/**
 * Props for ConnectionWizard
 */
export interface IConnectionWizardProps {
  initialUrl?: string;
  recentUrls?: string[];
  serverBaseUrl: string;
  onConnect: (url: string, mode: CredentialMode) => void;
  onCancel: () => void;
}

/**
 * Format credential mode for display
 */
function formatCredentialMode(mode: CredentialMode): string {
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
function UrlStep({
  backendUrl,
  recentUrls,
  onChange,
  error
}: {
  backendUrl: string;
  recentUrls: string[];
  onChange: (url: string) => void;
  error: string | null;
}): React.ReactElement {
  return (
    <div className="jp-ConnectionWizard-step">
      <h4>Step 1: Backend URL</h4>
      <p className="jp-ConnectionWizard-description">
        Enter the URL of your Dataing backend server.
      </p>

      <div className="jp-ConnectionWizard-field">
        <label htmlFor="backend-url">Backend URL</label>
        <input
          id="backend-url"
          type="url"
          value={backendUrl}
          onChange={e => onChange(e.target.value)}
          placeholder="http://localhost:8000"
          className="jp-ConnectionWizard-input"
          autoFocus
        />
      </div>

      {recentUrls.length > 0 && (
        <div className="jp-ConnectionWizard-recent">
          <label>Recent URLs</label>
          <div className="jp-ConnectionWizard-recent-list">
            {recentUrls.map(url => (
              <button
                key={url}
                type="button"
                className="jp-ConnectionWizard-recent-item"
                onClick={() => onChange(url)}
              >
                {url}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <div className="jp-ConnectionWizard-error">{error}</div>}
    </div>
  );
}

/**
 * Auth Step Component
 */
function AuthStep({
  credentialMode,
  apiKey,
  sessionOnly,
  keychainAvailable,
  onApiKeyChange,
  onSessionOnlyChange,
  error
}: {
  credentialMode: CredentialMode;
  apiKey: string;
  sessionOnly: boolean;
  keychainAvailable: boolean;
  onApiKeyChange: (key: string) => void;
  onSessionOnlyChange: (value: boolean) => void;
  error: string | null;
}): React.ReactElement {
  return (
    <div className="jp-ConnectionWizard-step">
      <h4>Step 2: Authentication</h4>

      <div className="jp-ConnectionWizard-mode">
        <span className="jp-ConnectionWizard-mode-label">Storage mode:</span>
        <span className="jp-ConnectionWizard-mode-value">
          {formatCredentialMode(credentialMode)}
        </span>
      </div>

      <p className="jp-ConnectionWizard-description">
        {credentialMode === 'keychain' &&
          'Your API key will be stored securely in your OS keychain.'}
        {credentialMode === 'env_var' &&
          'API key loaded from DATAING_API_KEY environment variable.'}
        {credentialMode === 'session' &&
          'API key will only be stored for this session.'}
      </p>

      <div className="jp-ConnectionWizard-field">
        <label htmlFor="api-key">API Key</label>
        <input
          id="api-key"
          type="password"
          value={apiKey}
          onChange={e => onApiKeyChange(e.target.value)}
          placeholder="Enter your Dataing API key"
          className="jp-ConnectionWizard-input"
          autoComplete="off"
        />
      </div>

      {keychainAvailable && credentialMode === 'keychain' && (
        <div className="jp-ConnectionWizard-checkbox">
          <label>
            <input
              type="checkbox"
              checked={sessionOnly}
              onChange={e => onSessionOnlyChange(e.target.checked)}
            />
            Don&apos;t store (session only)
          </label>
        </div>
      )}

      {error && <div className="jp-ConnectionWizard-error">{error}</div>}
    </div>
  );
}

/**
 * Test Step Component
 */
function TestStep({
  testing,
  testResult,
  onTest,
  error
}: {
  testing: boolean;
  testResult: ITestResult | null;
  onTest: () => void;
  error: string | null;
}): React.ReactElement {
  return (
    <div className="jp-ConnectionWizard-step">
      <h4>Step 3: Test Connection</h4>

      {!testResult && !testing && (
        <div>
          <p className="jp-ConnectionWizard-description">
            Click the button below to test your connection.
          </p>
          <button
            type="button"
            className="jp-ConnectionWizard-button jp-ConnectionWizard-button-primary"
            onClick={onTest}
          >
            Test Connection
          </button>
        </div>
      )}

      {testing && (
        <div className="jp-ConnectionWizard-testing">
          <span className="jp-ConnectionWizard-spinner" />
          <span>Testing connection...</span>
        </div>
      )}

      {testResult && !testing && (
        <div
          className={`jp-ConnectionWizard-result ${
            testResult.success
              ? 'jp-ConnectionWizard-result-success'
              : 'jp-ConnectionWizard-result-error'
          }`}
        >
          {testResult.success ? (
            <span>Connection successful!</span>
          ) : (
            <div>
              <strong>Connection failed</strong>
              <p>{testResult.error || 'Unknown error'}</p>
              <button
                type="button"
                className="jp-ConnectionWizard-button"
                onClick={onTest}
              >
                Retry
              </button>
            </div>
          )}
        </div>
      )}

      {error && <div className="jp-ConnectionWizard-error">{error}</div>}
    </div>
  );
}

/**
 * Confirm Step Component
 */
function ConfirmStep({
  backendUrl,
  credentialMode,
  saving,
  onSave,
  error
}: {
  backendUrl: string;
  credentialMode: CredentialMode;
  saving: boolean;
  onSave: () => void;
  error: string | null;
}): React.ReactElement {
  return (
    <div className="jp-ConnectionWizard-step">
      <h4>Step 4: Save Configuration</h4>

      <div className="jp-ConnectionWizard-summary">
        <div className="jp-ConnectionWizard-summary-row">
          <span className="jp-ConnectionWizard-summary-label">Backend URL:</span>
          <span className="jp-ConnectionWizard-summary-value">{backendUrl}</span>
        </div>
        <div className="jp-ConnectionWizard-summary-row">
          <span className="jp-ConnectionWizard-summary-label">
            Credential Storage:
          </span>
          <span className="jp-ConnectionWizard-summary-value">
            {formatCredentialMode(credentialMode)}
          </span>
        </div>
      </div>

      <button
        type="button"
        className="jp-ConnectionWizard-button jp-ConnectionWizard-button-primary"
        onClick={onSave}
        disabled={saving}
      >
        {saving ? 'Saving...' : 'Save & Connect'}
      </button>

      {error && <div className="jp-ConnectionWizard-error">{error}</div>}
    </div>
  );
}

/**
 * Main Connection Wizard Component
 */
export function ConnectionWizard({
  initialUrl = 'http://localhost:8000',
  recentUrls = [],
  serverBaseUrl,
  onConnect,
  onCancel
}: IConnectionWizardProps): React.ReactElement {
  const [state, setState] = React.useState<IWizardState>({
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

  // Fetch credential mode when URL changes
  React.useEffect(() => {
    if (state.step === 2 && state.backendUrl) {
      fetchCredentialMode();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.step, state.backendUrl]);

  const fetchCredentialMode = async (): Promise<void> => {
    try {
      const response = await fetch(`${serverBaseUrl}dataing/credentials`, {
        credentials: 'same-origin'
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
    } catch (error) {
      console.warn('Failed to fetch credential mode:', error);
    }
  };

  const testConnection = async (): Promise<void> => {
    setState(s => ({ ...s, testing: true, testResult: null, error: null }));

    try {
      const response = await fetch(`${serverBaseUrl}dataing/connection/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          base_url: state.backendUrl,
          api_key: state.apiKey
        })
      });

      const data = await response.json();
      setState(s => ({
        ...s,
        testing: false,
        testResult: {
          success: data.success,
          error: data.error
        }
      }));
    } catch (error) {
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

  const saveCredentials = async (): Promise<void> => {
    setState(s => ({ ...s, saving: true, error: null }));

    try {
      const effectiveMode = state.sessionOnly ? 'session' : state.credentialMode;

      const response = await fetch(`${serverBaseUrl}dataing/credentials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          base_url: state.backendUrl,
          api_key: state.apiKey,
          mode: effectiveMode
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to save credentials');
      }

      setState(s => ({ ...s, saving: false }));
      onConnect(state.backendUrl, effectiveMode);
    } catch (error) {
      setState(s => ({
        ...s,
        saving: false,
        error: error instanceof Error ? error.message : 'Failed to save'
      }));
    }
  };

  const goToStep = (step: number): void => {
    setState(s => ({ ...s, step, error: null }));
  };

  const canProceed = (): boolean => {
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

  return (
    <div className="jp-ConnectionWizard">
      <div className="jp-ConnectionWizard-header">
        <h3>Connect to Dataing</h3>
        <button
          type="button"
          className="jp-ConnectionWizard-close"
          onClick={onCancel}
          aria-label="Cancel"
        >
          &times;
        </button>
      </div>

      <div className="jp-ConnectionWizard-progress">
        {[1, 2, 3, 4].map(step => (
          <div
            key={step}
            className={`jp-ConnectionWizard-progress-step ${
              state.step === step
                ? 'jp-ConnectionWizard-progress-step-active'
                : state.step > step
                  ? 'jp-ConnectionWizard-progress-step-complete'
                  : ''
            }`}
          >
            {step}
          </div>
        ))}
      </div>

      <div className="jp-ConnectionWizard-content">
        {state.step === 1 && (
          <UrlStep
            backendUrl={state.backendUrl}
            recentUrls={recentUrls}
            onChange={url => setState(s => ({ ...s, backendUrl: url }))}
            error={state.error}
          />
        )}

        {state.step === 2 && (
          <AuthStep
            credentialMode={state.credentialMode}
            apiKey={state.apiKey}
            sessionOnly={state.sessionOnly}
            keychainAvailable={state.credentialMode === 'keychain'}
            onApiKeyChange={key => setState(s => ({ ...s, apiKey: key }))}
            onSessionOnlyChange={value =>
              setState(s => ({ ...s, sessionOnly: value }))
            }
            error={state.error}
          />
        )}

        {state.step === 3 && (
          <TestStep
            testing={state.testing}
            testResult={state.testResult}
            onTest={testConnection}
            error={state.error}
          />
        )}

        {state.step === 4 && (
          <ConfirmStep
            backendUrl={state.backendUrl}
            credentialMode={
              state.sessionOnly ? 'session' : state.credentialMode
            }
            saving={state.saving}
            onSave={saveCredentials}
            error={state.error}
          />
        )}
      </div>

      <div className="jp-ConnectionWizard-footer">
        {state.step > 1 && (
          <button
            type="button"
            className="jp-ConnectionWizard-button"
            onClick={() => goToStep(state.step - 1)}
          >
            Back
          </button>
        )}

        <div className="jp-ConnectionWizard-footer-spacer" />

        {state.step < 4 && (
          <button
            type="button"
            className="jp-ConnectionWizard-button jp-ConnectionWizard-button-primary"
            onClick={() => goToStep(state.step + 1)}
            disabled={!canProceed()}
          >
            Next
          </button>
        )}
      </div>
    </div>
  );
}
