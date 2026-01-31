-- Test tracking tables for measuring codify effectiveness
-- Tracks generated tests, adoption status, and test run results

-- Generated tests table
CREATE TABLE IF NOT EXISTS generated_tests (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    format VARCHAR(20) NOT NULL,
    test_type VARCHAR(50) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    column_name VARCHAR(255),
    description TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    adopted_at TIMESTAMP WITH TIME ZONE,
    adopted_by VARCHAR(255),
    last_run_at TIMESTAMP WITH TIME ZONE,
    run_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0
);

-- Test runs table
CREATE TABLE IF NOT EXISTS test_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id UUID NOT NULL REFERENCES generated_tests(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    passed BOOLEAN NOT NULL,
    failure_message TEXT,
    run_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_generated_tests_tenant ON generated_tests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_generated_tests_investigation ON generated_tests(investigation_id);
CREATE INDEX IF NOT EXISTS idx_generated_tests_created ON generated_tests(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_generated_tests_adopted ON generated_tests(tenant_id, adopted_at) WHERE adopted_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_test_runs_test ON test_runs(test_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_tenant ON test_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_failures ON test_runs(tenant_id, run_at DESC) WHERE passed = FALSE;
