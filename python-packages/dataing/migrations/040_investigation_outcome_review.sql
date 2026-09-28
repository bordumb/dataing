-- 040: a person's verdict on an investigation's root cause (spec 0001 §7.10).
-- Confirmed runs feed the resolution event; both verdicts feed the feedback log.

ALTER TABLE issue_investigation_runs
    ADD COLUMN outcome_verdict TEXT CHECK (outcome_verdict IN ('confirmed', 'rejected')),
    ADD COLUMN outcome_note TEXT,
    ADD COLUMN outcome_reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN outcome_reviewed_at TIMESTAMPTZ;
