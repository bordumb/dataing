-- Runbooks and knowledge base
-- Migration: 022_runbooks.sql

-- Runbooks table - knowledge base articles generated from resolved issues
CREATE TABLE IF NOT EXISTS runbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    summary TEXT,

    -- Categorization
    dataset_id TEXT,
    labels TEXT[] NOT NULL DEFAULT '{}',

    -- Origin tracking
    created_from_issue_id UUID REFERENCES issues(id) ON DELETE SET NULL,
    created_from_investigation_id UUID REFERENCES investigations(id) ON DELETE SET NULL,

    -- Structured content (extracted from investigation)
    symptoms JSONB NOT NULL DEFAULT '[]',
    root_cause TEXT,
    verification_steps JSONB NOT NULL DEFAULT '[]',
    fix_steps JSONB NOT NULL DEFAULT '[]',
    prevention_notes TEXT,

    -- Search and similarity
    search_vector tsvector,
    embedding_vector FLOAT8[],

    -- Metadata
    is_published BOOLEAN NOT NULL DEFAULT false,
    view_count INT NOT NULL DEFAULT 0,
    usefulness_score FLOAT NOT NULL DEFAULT 0.0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL
);

-- Index for tenant queries
CREATE INDEX IF NOT EXISTS idx_runbooks_tenant_id ON runbooks(tenant_id);

-- Index for dataset-based queries
CREATE INDEX IF NOT EXISTS idx_runbooks_dataset_id ON runbooks(dataset_id);

-- Index for origin tracking
CREATE INDEX IF NOT EXISTS idx_runbooks_created_from_issue ON runbooks(created_from_issue_id);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_runbooks_search ON runbooks USING GIN(search_vector);

-- Index for labels (GIN for array containment)
CREATE INDEX IF NOT EXISTS idx_runbooks_labels ON runbooks USING GIN(labels);

-- Trigger to update search_vector on insert/update
CREATE OR REPLACE FUNCTION update_runbook_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.summary, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.body, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.root_cause, '')), 'B');
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_runbook_search_vector
    BEFORE INSERT OR UPDATE ON runbooks
    FOR EACH ROW
    EXECUTE FUNCTION update_runbook_search_vector();

-- Runbook links - associations between runbooks and issues
CREATE TABLE IF NOT EXISTS runbook_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    runbook_id UUID NOT NULL REFERENCES runbooks(id) ON DELETE CASCADE,
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,

    -- Similarity/relevance score (0.0 to 1.0)
    score FLOAT NOT NULL DEFAULT 0.0,

    -- Link type
    link_type TEXT NOT NULL DEFAULT 'suggested',  -- 'suggested', 'applied', 'referenced'

    -- Feedback
    was_helpful BOOLEAN,
    feedback_notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Prevent duplicate links
    CONSTRAINT uq_runbook_issue UNIQUE (runbook_id, issue_id)
);

-- Index for issue lookups
CREATE INDEX IF NOT EXISTS idx_runbook_links_issue ON runbook_links(issue_id);

-- Index for runbook lookups
CREATE INDEX IF NOT EXISTS idx_runbook_links_runbook ON runbook_links(runbook_id);

-- Index for score-based sorting
CREATE INDEX IF NOT EXISTS idx_runbook_links_score ON runbook_links(score DESC);
