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
 * Main Connection Wizard Component
 */
export declare function ConnectionWizard({ initialUrl, recentUrls, serverBaseUrl, onConnect, onCancel }: IConnectionWizardProps): React.ReactElement;
