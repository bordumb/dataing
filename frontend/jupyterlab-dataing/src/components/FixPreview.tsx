/**
 * Fix Preview Widget - Displays fix proposals with syntax highlighting and actions.
 */

import * as React from 'react';
import type { IFixProposal, IFixValidationResult, FixType } from '../types';

/**
 * Props for FixPreview component
 */
export interface IFixPreviewProps {
  proposal: IFixProposal;
  onPreviewImpact?: () => Promise<IFixValidationResult>;
  onApply?: () => Promise<void>;
  onCopy?: () => void;
  disabled?: boolean;
}

/**
 * Get language for syntax highlighting based on fix type
 */
function getLanguage(fixType: FixType): string {
  switch (fixType) {
    case 'sql_ddl':
    case 'sql_dml':
      return 'sql';
    case 'dbt_patch':
      return 'sql'; // dbt SQL with Jinja
    case 'python_patch':
      return 'python';
    case 'manual_instruction':
    default:
      return 'text';
  }
}

/**
 * Get display label for fix type
 */
function getFixTypeLabel(fixType: FixType): string {
  switch (fixType) {
    case 'sql_ddl':
      return 'SQL DDL (Schema Change)';
    case 'sql_dml':
      return 'SQL DML (Data Change)';
    case 'dbt_patch':
      return 'dbt Model Patch';
    case 'python_patch':
      return 'Python Code Patch';
    case 'manual_instruction':
      return 'Manual Instructions';
    default:
      return fixType;
  }
}

/**
 * Get confidence color based on value
 */
function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) {
    return 'var(--jp-success-color1, #4caf50)';
  } else if (confidence >= 0.7) {
    return 'var(--jp-warn-color1, #ff9800)';
  } else {
    return 'var(--jp-error-color1, #f44336)';
  }
}

/**
 * Code Block with syntax highlighting (basic implementation)
 */
function CodeBlock({
  code,
  language
}: {
  code: string;
  language: string;
}): React.ReactElement {
  return (
    <pre className="jp-FixPreview-code" data-language={language}>
      <code>{code}</code>
    </pre>
  );
}

/**
 * Risk Warning Component
 */
function RiskWarning({ risk }: { risk: string }): React.ReactElement {
  return (
    <div className="jp-FixPreview-risk">
      <span className="jp-FixPreview-risk-icon" role="img" aria-label="warning">
        &#x26A0;
      </span>
      <span>{risk}</span>
    </div>
  );
}

/**
 * Fix Preview Component State
 */
interface IFixPreviewState {
  isExpanded: boolean;
  showRollback: boolean;
  confirmed: boolean;
  previewResult: IFixValidationResult | null;
  previewing: boolean;
  applying: boolean;
  error: string | null;
}

/**
 * Main Fix Preview Component
 */
export function FixPreview({
  proposal,
  onPreviewImpact,
  onApply,
  onCopy,
  disabled = false
}: IFixPreviewProps): React.ReactElement {
  const [state, setState] = React.useState<IFixPreviewState>({
    isExpanded: true,
    showRollback: false,
    confirmed: false,
    previewResult: null,
    previewing: false,
    applying: false,
    error: null
  });

  const language = getLanguage(proposal.fix_type);
  const confidenceColor = getConfidenceColor(proposal.confidence);
  const confidencePercent = Math.round(proposal.confidence * 100);

  const handlePreviewImpact = async (): Promise<void> => {
    if (!onPreviewImpact) return;

    setState(s => ({ ...s, previewing: true, error: null }));
    try {
      const result = await onPreviewImpact();
      setState(s => ({ ...s, previewing: false, previewResult: result }));
    } catch (error) {
      setState(s => ({
        ...s,
        previewing: false,
        error: error instanceof Error ? error.message : 'Preview failed'
      }));
    }
  };

  const handleApply = async (): Promise<void> => {
    if (!onApply || !state.confirmed) return;

    setState(s => ({ ...s, applying: true, error: null }));
    try {
      await onApply();
      setState(s => ({ ...s, applying: false }));
    } catch (error) {
      setState(s => ({
        ...s,
        applying: false,
        error: error instanceof Error ? error.message : 'Apply failed'
      }));
    }
  };

  const handleCopy = (): void => {
    navigator.clipboard.writeText(proposal.code).catch(() => {
      // Fallback for environments without clipboard API
      console.warn('Clipboard API not available');
    });
    onCopy?.();
  };

  const toggleExpanded = (): void => {
    setState(s => ({ ...s, isExpanded: !s.isExpanded }));
  };

  const toggleRollback = (): void => {
    setState(s => ({ ...s, showRollback: !s.showRollback }));
  };

  const toggleConfirmed = (): void => {
    setState(s => ({ ...s, confirmed: !s.confirmed }));
  };

  return (
    <div className="jp-FixPreview">
      {/* Header */}
      <div className="jp-FixPreview-header" onClick={toggleExpanded}>
        <div className="jp-FixPreview-header-left">
          <span
            className="jp-FixPreview-icon"
            role="img"
            aria-label="lightbulb"
          >
            &#x1F4A1;
          </span>
          <span className="jp-FixPreview-title">Proposed Fix</span>
          <span
            className="jp-FixPreview-confidence"
            style={{ color: confidenceColor }}
          >
            (confidence: {confidencePercent}%)
          </span>
        </div>
        <div className="jp-FixPreview-header-right">
          <span className="jp-FixPreview-type">{getFixTypeLabel(proposal.fix_type)}</span>
          <span className={`jp-FixPreview-chevron ${state.isExpanded ? 'expanded' : ''}`}>
            &#x25BC;
          </span>
        </div>
      </div>

      {/* Expanded Content */}
      {state.isExpanded && (
        <div className="jp-FixPreview-content">
          {/* Description */}
          <p className="jp-FixPreview-description">{proposal.description}</p>

          {/* Code Block */}
          <div className="jp-FixPreview-code-container">
            <CodeBlock code={proposal.code} language={language} />
          </div>

          {/* Risks */}
          {proposal.risks.length > 0 && (
            <div className="jp-FixPreview-risks">
              <div className="jp-FixPreview-risks-header">
                <span className="jp-FixPreview-risks-icon" role="img" aria-label="warning">
                  &#x26A0;&#xFE0F;
                </span>
                <span>Risks:</span>
              </div>
              {proposal.risks.map((risk, index) => (
                <RiskWarning key={index} risk={risk} />
              ))}
            </div>
          )}

          {/* Estimated Impact */}
          <div className="jp-FixPreview-impact">
            <span className="jp-FixPreview-impact-icon" role="img" aria-label="chart">
              &#x1F4CA;
            </span>
            <span>Estimated Impact: {proposal.estimated_impact}</span>
          </div>

          {/* Target Asset */}
          <div className="jp-FixPreview-target">
            <span>Target: </span>
            <code className="jp-FixPreview-target-asset">{proposal.target_asset}</code>
          </div>

          {/* Rollback (collapsible) */}
          {proposal.rollback && (
            <div className="jp-FixPreview-rollback">
              <button
                type="button"
                className="jp-FixPreview-rollback-toggle"
                onClick={toggleRollback}
              >
                <span className={`jp-FixPreview-chevron ${state.showRollback ? 'expanded' : ''}`}>
                  &#x25B6;
                </span>
                <span>Rollback Statement</span>
              </button>
              {state.showRollback && (
                <div className="jp-FixPreview-rollback-code">
                  <CodeBlock code={proposal.rollback} language={language} />
                </div>
              )}
            </div>
          )}

          {/* Preview Result */}
          {state.previewResult && (
            <div
              className={`jp-FixPreview-preview-result ${
                state.previewResult.is_valid
                  ? 'jp-FixPreview-preview-result-valid'
                  : 'jp-FixPreview-preview-result-invalid'
              }`}
            >
              <div className="jp-FixPreview-preview-result-header">
                {state.previewResult.is_valid ? (
                  <span>&#x2705; Fix validated successfully</span>
                ) : (
                  <span>&#x274C; Fix validation failed</span>
                )}
              </div>
              {state.previewResult.estimated_affected_rows !== null && (
                <div>
                  Estimated affected rows: {state.previewResult.estimated_affected_rows.toLocaleString()}
                </div>
              )}
              {state.previewResult.errors.length > 0 && (
                <ul className="jp-FixPreview-preview-errors">
                  {state.previewResult.errors.map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                </ul>
              )}
              {state.previewResult.warnings.length > 0 && (
                <ul className="jp-FixPreview-preview-warnings">
                  {state.previewResult.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Error Display */}
          {state.error && (
            <div className="jp-FixPreview-error">
              {state.error}
            </div>
          )}

          {/* Actions */}
          <div className="jp-FixPreview-actions">
            {/* Preview Impact Button */}
            {onPreviewImpact && (
              <button
                type="button"
                className="jp-FixPreview-button"
                onClick={handlePreviewImpact}
                disabled={disabled || state.previewing}
              >
                {state.previewing ? 'Previewing...' : 'Preview Impact'}
              </button>
            )}

            {/* Copy Button */}
            <button
              type="button"
              className="jp-FixPreview-button"
              onClick={handleCopy}
              disabled={disabled}
            >
              Copy
            </button>

            {/* Confirmation Checkbox */}
            {proposal.requires_confirmation && onApply && (
              <label className="jp-FixPreview-confirm">
                <input
                  type="checkbox"
                  checked={state.confirmed}
                  onChange={toggleConfirmed}
                  disabled={disabled || state.applying}
                />
                <span>I understand the risks</span>
              </label>
            )}

            {/* Apply Button */}
            {onApply && (
              <button
                type="button"
                className="jp-FixPreview-button jp-FixPreview-button-primary"
                onClick={handleApply}
                disabled={
                  disabled ||
                  state.applying ||
                  (proposal.requires_confirmation && !state.confirmed)
                }
              >
                {state.applying ? 'Applying...' : 'Apply'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
