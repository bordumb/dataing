-- Dataset registry for UUID-based dataset identification
-- Datasets are synced from data sources on schema discovery

CREATE TABLE datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    datasource_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    native_path VARCHAR(500) NOT NULL,
    name VARCHAR(255) NOT NULL,
    table_type VARCHAR(50) NOT NULL DEFAULT 'table',
    schema_name VARCHAR(255),
    catalog_name VARCHAR(255),
    row_count BIGINT,
    size_bytes BIGINT,
    column_count INTEGER,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(datasource_id, native_path)
);

CREATE INDEX idx_datasets_tenant ON datasets(tenant_id);
CREATE INDEX idx_datasets_datasource ON datasets(datasource_id);
CREATE INDEX idx_datasets_native_path ON datasets(native_path);
CREATE INDEX idx_datasets_name ON datasets(name);
