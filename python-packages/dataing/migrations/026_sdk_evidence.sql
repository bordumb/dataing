-- SDK Evidence table for rich, queryable, tamper-evident evidence
-- Part of fn-20: Evidence Schema

-- Evidence table with discriminated union support
CREATE TABLE IF NOT EXISTS sdk_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES sdk_runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    kind VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    prev_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint for ordering within a run
    UNIQUE(run_id, seq)
);

-- Index for querying by kind across all runs
CREATE INDEX IF NOT EXISTS idx_sdk_evidence_kind ON sdk_evidence(kind);

-- Composite index for filtering by run and kind
CREATE INDEX IF NOT EXISTS idx_sdk_evidence_run_kind ON sdk_evidence(run_id, kind);

-- Index for hash chain verification
CREATE INDEX IF NOT EXISTS idx_sdk_evidence_content_hash ON sdk_evidence(content_hash);

-- GIN index for JSONB content queries
CREATE INDEX IF NOT EXISTS idx_sdk_evidence_content ON sdk_evidence USING GIN (content);

COMMENT ON TABLE sdk_evidence IS 'Rich evidence records from SDK investigation runs';
COMMENT ON COLUMN sdk_evidence.kind IS 'Evidence type discriminator: query_result, hypothesis, lineage_trace, schema_snapshot, metric_calculation, run_summary';
COMMENT ON COLUMN sdk_evidence.content IS 'JSONB content specific to evidence kind';
COMMENT ON COLUMN sdk_evidence.content_hash IS 'SHA256 hash of content for tamper-evidence';
COMMENT ON COLUMN sdk_evidence.prev_hash IS 'Hash of previous evidence in chain (NULL for first)';
