-- RL Training Signals table for ML pipeline
-- Captures input/output pairs with reward signals for future RL training

CREATE TABLE IF NOT EXISTS rl_training_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What are we training?
    signal_type TEXT NOT NULL,  -- 'interpretation', 'synthesis'

    -- Input/output pair
    input_context JSONB NOT NULL,
    output_response JSONB NOT NULL,

    -- Reward signals (sparse - not all will be present)
    automated_score FLOAT,
    automated_dimensions JSONB,  -- {causal_depth, specificity, actionability}
    human_feedback_score FLOAT,  -- From thumbs up/down (-1, 0, 1)
    outcome_score FLOAT,  -- Did the fix work?

    -- Composite reward (computed by RL pipeline, not at insert time)
    computed_reward FLOAT,
    reward_computed_at TIMESTAMPTZ,

    -- Linkage
    tenant_id UUID NOT NULL,
    investigation_id UUID NOT NULL,
    source_event_id UUID,

    -- Metadata
    model_version TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- For RL batch queries
    is_used_for_training BOOLEAN DEFAULT FALSE,
    training_batch_id UUID
);

-- Index for RL pipeline batch queries
CREATE INDEX IF NOT EXISTS idx_rl_signals_training
    ON rl_training_signals(signal_type, is_used_for_training, created_at);

-- Index for investigation lookups
CREATE INDEX IF NOT EXISTS idx_rl_signals_investigation
    ON rl_training_signals(investigation_id);

-- Index for tenant scoping
CREATE INDEX IF NOT EXISTS idx_rl_signals_tenant
    ON rl_training_signals(tenant_id);

COMMENT ON TABLE rl_training_signals IS 'Training signals for RL pipeline - captures LLM input/output pairs with reward signals';
COMMENT ON COLUMN rl_training_signals.signal_type IS 'Type of LLM output: interpretation or synthesis';
COMMENT ON COLUMN rl_training_signals.automated_score IS 'Composite score from LLM-as-judge (0.0-1.0)';
COMMENT ON COLUMN rl_training_signals.automated_dimensions IS 'Dimensional scores: {causal_depth, specificity, actionability}';
COMMENT ON COLUMN rl_training_signals.human_feedback_score IS 'User feedback: -1 (bad), 0 (neutral), 1 (good)';
COMMENT ON COLUMN rl_training_signals.outcome_score IS 'Did the root cause determination lead to a fix? (computed async)';
