-- Schema field comments (threaded)
CREATE TABLE schema_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    field_name VARCHAR(255) NOT NULL,
    parent_id UUID REFERENCES schema_comments(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    author_id UUID,
    author_name VARCHAR(255),
    upvotes INT DEFAULT 0,
    downvotes INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_schema_comments_dataset ON schema_comments(tenant_id, dataset_id, field_name);
CREATE INDEX idx_schema_comments_parent ON schema_comments(parent_id);
