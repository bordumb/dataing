-- Migration: 023_drop_investigation_jobs.sql
-- Description: Drop the investigation_jobs table (replaced by Temporal workflows)
--
-- Pre-Requisites:
-- Before running this migration, ensure:
-- 1. INVESTIGATION_ENGINE=temporal is set (not arq)
-- 2. No Arq workers are running
-- 3. Verify no pending jobs:
--    SELECT COUNT(*) FROM investigation_jobs
--    WHERE status NOT IN ('completed', 'failed', 'cancelled');
-- 4. Optionally backup data for audit:
--    CREATE TABLE investigation_jobs_archive AS SELECT * FROM investigation_jobs;
--
-- Background:
-- The investigation_jobs table was used by the Arq-based job queue system.
-- With the Temporal migration (fn-16), all investigation execution is now
-- handled by Temporal workflows which provide built-in durability,
-- checkpointing, and cancellation.

DROP TABLE IF EXISTS investigation_jobs;
