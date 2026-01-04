/**
 * Schema types for dynamic form generation.
 *
 * These types define the structure of form field configurations
 * that can be loaded from the backend or defined statically.
 */

export type FieldType =
  | 'text'
  | 'password'
  | 'number'
  | 'select'
  | 'checkbox'
  | 'textarea'
  | 'file'

export interface SelectOption {
  value: string
  label: string
}

export interface FieldSchema {
  name: string
  label: string
  type: FieldType
  required?: boolean
  placeholder?: string
  description?: string
  defaultValue?: string | number | boolean
  options?: SelectOption[] // For select fields
  min?: number // For number fields
  max?: number // For number fields
  pattern?: string // Regex pattern for validation
  dependsOn?: {
    field: string
    value: string | string[]
  }
}

export interface FormSchema {
  fields: FieldSchema[]
}

// Predefined schemas for data source types
export const DATA_SOURCE_SCHEMAS: Record<string, FormSchema> = {
  postgresql: {
    fields: [
      { name: 'host', label: 'Host', type: 'text', required: true, placeholder: 'localhost' },
      { name: 'port', label: 'Port', type: 'number', required: true, defaultValue: 5432 },
      { name: 'database', label: 'Database', type: 'text', required: true },
      { name: 'username', label: 'Username', type: 'text', required: true },
      { name: 'password', label: 'Password', type: 'password', required: true },
      { name: 'ssl_mode', label: 'SSL Mode', type: 'select', options: [
        { value: 'disable', label: 'Disable' },
        { value: 'require', label: 'Require' },
        { value: 'verify-ca', label: 'Verify CA' },
        { value: 'verify-full', label: 'Verify Full' },
      ]},
    ],
  },
  mysql: {
    fields: [
      { name: 'host', label: 'Host', type: 'text', required: true, placeholder: 'localhost' },
      { name: 'port', label: 'Port', type: 'number', required: true, defaultValue: 3306 },
      { name: 'database', label: 'Database', type: 'text', required: true },
      { name: 'username', label: 'Username', type: 'text', required: true },
      { name: 'password', label: 'Password', type: 'password', required: true },
    ],
  },
  snowflake: {
    fields: [
      { name: 'account', label: 'Account', type: 'text', required: true, placeholder: 'your-account.snowflakecomputing.com' },
      { name: 'warehouse', label: 'Warehouse', type: 'text', required: true },
      { name: 'database', label: 'Database', type: 'text', required: true },
      { name: 'schema', label: 'Schema', type: 'text', placeholder: 'public' },
      { name: 'username', label: 'Username', type: 'text', required: true },
      { name: 'password', label: 'Password', type: 'password', required: true },
      { name: 'role', label: 'Role', type: 'text', placeholder: 'ACCOUNTADMIN' },
    ],
  },
  bigquery: {
    fields: [
      { name: 'project_id', label: 'Project ID', type: 'text', required: true },
      { name: 'dataset', label: 'Dataset', type: 'text' },
      { name: 'credentials_json', label: 'Service Account JSON', type: 'textarea', required: true, description: 'Paste your service account credentials JSON' },
      { name: 'location', label: 'Location', type: 'text', placeholder: 'US' },
    ],
  },
  redshift: {
    fields: [
      { name: 'host', label: 'Host', type: 'text', required: true },
      { name: 'port', label: 'Port', type: 'number', required: true, defaultValue: 5439 },
      { name: 'database', label: 'Database', type: 'text', required: true },
      { name: 'username', label: 'Username', type: 'text', required: true },
      { name: 'password', label: 'Password', type: 'password', required: true },
      { name: 'schema', label: 'Schema', type: 'text', placeholder: 'public' },
    ],
  },
  trino: {
    fields: [
      { name: 'host', label: 'Host', type: 'text', required: true },
      { name: 'port', label: 'Port', type: 'number', required: true, defaultValue: 8080 },
      { name: 'catalog', label: 'Catalog', type: 'text', required: true },
      { name: 'schema', label: 'Schema', type: 'text' },
      { name: 'username', label: 'Username', type: 'text', required: true },
      { name: 'password', label: 'Password', type: 'password' },
    ],
  },
  duckdb: {
    fields: [
      { name: 'path', label: 'Database Path', type: 'text', required: true, placeholder: '/path/to/database.duckdb', description: 'Path to DuckDB file or :memory: for in-memory' },
    ],
  },
  mongodb: {
    fields: [
      { name: 'connection_string', label: 'Connection String', type: 'text', required: true, placeholder: 'mongodb://localhost:27017', description: 'MongoDB connection URI' },
      { name: 'database', label: 'Database', type: 'text', required: true },
    ],
  },
  s3: {
    fields: [
      { name: 'bucket', label: 'Bucket', type: 'text', required: true },
      { name: 'prefix', label: 'Prefix', type: 'text', placeholder: 'data/' },
      { name: 'region', label: 'Region', type: 'text', required: true, defaultValue: 'us-east-1' },
      { name: 'access_key_id', label: 'Access Key ID', type: 'text', required: true },
      { name: 'secret_access_key', label: 'Secret Access Key', type: 'password', required: true },
      { name: 'file_format', label: 'File Format', type: 'select', options: [
        { value: 'parquet', label: 'Parquet' },
        { value: 'csv', label: 'CSV' },
        { value: 'json', label: 'JSON' },
      ]},
    ],
  },
  gcs: {
    fields: [
      { name: 'bucket', label: 'Bucket', type: 'text', required: true },
      { name: 'prefix', label: 'Prefix', type: 'text', placeholder: 'data/' },
      { name: 'credentials_json', label: 'Service Account JSON', type: 'textarea', required: true },
      { name: 'file_format', label: 'File Format', type: 'select', options: [
        { value: 'parquet', label: 'Parquet' },
        { value: 'csv', label: 'CSV' },
        { value: 'json', label: 'JSON' },
      ]},
    ],
  },
}

export function getSchemaForType(type: string): FormSchema {
  return DATA_SOURCE_SCHEMAS[type] || {
    fields: [
      { name: 'host', label: 'Host', type: 'text', required: true },
      { name: 'port', label: 'Port', type: 'number' },
      { name: 'database', label: 'Database', type: 'text' },
      { name: 'username', label: 'Username', type: 'text' },
      { name: 'password', label: 'Password', type: 'password' },
    ],
  }
}
