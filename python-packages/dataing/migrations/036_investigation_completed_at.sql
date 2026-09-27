-- Record when an investigation completes.
-- investigations.status is generated from outcome, but nothing records when the
-- outcome was set. A trigger stamps completed_at the first time outcome becomes
-- non-null (and clears it if the outcome is cleared), so writers only set outcome.
-- Re-runnable: every statement is idempotent.

ALTER TABLE investigations ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

COMMENT ON COLUMN investigations.completed_at IS
    'When outcome was first set (NULL while the investigation is active)';

CREATE OR REPLACE FUNCTION set_investigation_completed_at() RETURNS trigger AS $$
BEGIN
    IF NEW.outcome IS NULL THEN
        NEW.completed_at := NULL;
    ELSIF NEW.completed_at IS NULL THEN
        NEW.completed_at := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS investigations_set_completed_at ON investigations;
CREATE TRIGGER investigations_set_completed_at
    BEFORE INSERT OR UPDATE OF outcome ON investigations
    FOR EACH ROW EXECUTE FUNCTION set_investigation_completed_at();

-- Investigations completed before this migration: the completion time is unknown,
-- so use the creation time.
UPDATE investigations
SET completed_at = created_at
WHERE outcome IS NOT NULL AND completed_at IS NULL;
