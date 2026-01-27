-- Add root_hash to investigations table for evidence chain integrity.
-- Part of fn-33.2: Bridge Temporal workflow evidence to hash chain.

ALTER TABLE investigations ADD COLUMN IF NOT EXISTS root_hash VARCHAR(64);

COMMENT ON COLUMN investigations.root_hash IS
    'SHA-256 hash of final evidence item in chain (NULL if not finalized)';
