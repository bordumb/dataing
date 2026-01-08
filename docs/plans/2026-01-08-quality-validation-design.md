# LLM Output Quality Validation Design

## Overview

Add semantic quality validation to LLM outputs using an LLM-as-judge approach. This enforces that interpretations and syntheses explain *why* anomalies occurred, not just *what* was observed.

The system is designed with hexagonal architecture to support swapping validation strategies (regex, LLM-judge, RL-based) and captures training signals for a future reinforcement learning pipeline.

## Problem Statement

Current LLM outputs often produce shallow reasoning:

> "The query results strongly support the hypothesis... indicating a complete breakdown in the user-order relationship join process."

This confirms the symptom exists but doesn't explain the root cause. We need outputs like:

> "The 485 orphaned orders all appeared after 03:14 UTC when the users ETL job timed out due to API rate limiting. This caused the users table to stop receiving updates, breaking the JOIN for any orders with user_ids created after that timestamp."

## Architecture

### Hexagonal Design

```
┌─────────────────────────────────────────────────────────┐
│  QualityValidator Protocol (Port)                       │
│  - validate_interpretation(response) -> ValidationResult│
│  - validate_synthesis(response) -> ValidationResult     │
└─────────────────────────────────────────────────────────┘
          ▲              ▲              ▲
          │              │              │
   ┌──────┴───┐   ┌──────┴───┐   ┌──────┴───┐
   │  Regex   │   │ LLM-as-  │   │ RL-based │
   │ Adapter  │   │  Judge   │   │ Adapter  │
   └──────────┘   └──────────┘   └──────────┘
```

Initial implementation uses LLM-as-judge. The protocol allows swapping to regex-based (cheaper, less flexible) or RL-based (learned from feedback) validators later.

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Investigation Execution                          │
├─────────────────────────────────────────────────────────────────────┤
│  LLM Call (interpret_evidence / synthesize_findings)                 │
│    ↓                                                                 │
│  Pydantic AI Validation (structural)                                 │
│    ↓                                                                 │
│  QualityValidator.validate() ──→ investigation_feedback_events       │
│    ↓                               (audit log)                       │
│    ↓                                                                 │
│    └──────────────────────────→ rl_training_signals                  │
│                                   (ML training data)                 │
└─────────────────────────────────────────────────────────────────────┘
```

## What Gets Validated

| Stage | Validated? | Rationale |
|-------|------------|-----------|
| `generate_hypotheses()` | No | Structural validation sufficient; bad hypotheses filter naturally through evidence |
| `generate_query()` | No | Database execution validates SQL; reflexion handles errors |
| `interpret_evidence()` | **Yes** | Where shallow reasoning happens; feeds into synthesis |
| `synthesize_findings()` | **Yes** | User-facing output; must explain root cause |

Cost impact: ~30% overhead (6 judge calls per investigation with 5 hypotheses). Interpretation validations run in parallel.

## Quality Dimensions

Single LLM-as-judge call returns three dimensional scores:

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| `causal_depth` | 50% | Does it explain WHY, not just WHAT? Full causal chain with mechanism. |
| `specificity` | 30% | Concrete data points: timestamps, counts, table/column names. |
| `actionability` | 20% | Recommendations specific enough to act on (exact commands, not "investigate"). |

### Scoring Rubric

**Causal Depth:**
- 0.0-0.2: Restates symptom ("NULLs exist")
- 0.3-0.4: Names cause without mechanism ("upstream issue")
- 0.5-0.6: Cause + effect but missing intermediate steps
- 0.7-0.8: Full chain but vague on timing/mechanism
- 0.9-1.0: Complete chain with timing ("ETL timeout at 03:14 -> stale table -> JOIN NULLs")

**Specificity:**
- 0.0-0.2: No concrete data
- 0.3-0.4: Vague quantities ("many rows")
- 0.5-0.6: Some numbers but no timestamps
- 0.7-0.8: Numbers + timestamps OR entity names
- 0.9-1.0: Timestamps + counts + specific table/column names

**Actionability:**
- 0.0-0.2: "Investigate the issue"
- 0.3-0.4: "Check the ETL job"
- 0.5-0.6: "Check the stg_users ETL job logs"
- 0.7-0.8: "Check CloudWatch for stg_users job failures around 03:14 UTC"
- 0.9-1.0: "Run: `airflow trigger_dag stg_users --conf '{\"backfill\": true}'`"

Composite score: `causal_depth * 0.5 + specificity * 0.3 + actionability * 0.2`

Pass threshold: 0.6 (configurable)

## Response Model Changes

### InterpretationResponse

Add required structured fields to force the LLM to "show its work":

```python
class InterpretationResponse(BaseModel):
    supports_hypothesis: bool | None
    confidence: float  # 0.0-1.0
    interpretation: str  # min 50 chars

    # NEW: Required structured reasoning
    causal_chain: str  # min 30 chars
    # Example: "users ETL stopped at 03:14 -> stale table -> JOIN NULLs"

    key_findings: list[str]  # 1-5 items with data points

    next_investigation_step: str | None
    # Required if inconclusive
```

### SynthesisResponse

```python
class SynthesisResponse(BaseModel):
    root_cause: str | None  # Must explain WHY, not WHAT
    confidence: float  # 0.0-1.0

    # NEW: Required structured fields
    causal_chain: list[str]  # 2-6 steps from cause to symptom
    # Example: ["API rate limit", "ETL timeout", "stale users table", "JOIN NULLs"]

    estimated_onset: str  # min 5 chars (timestamp or relative)
    affected_scope: str  # min 10 chars (blast radius)

    supporting_evidence: list[str]  # 1-10 items
    recommendations: list[str]  # 1-5 actionable items
```

### HypothesisResponse

```python
class HypothesisResponse(BaseModel):
    id: str
    title: str  # 15-200 chars
    category: HypothesisCategory
    reasoning: str  # min 30 chars
    suggested_query: str

    # NEW: Testability criteria
    expected_if_true: str  # min 10 chars
    expected_if_false: str  # min 10 chars
```

## Training Signal Capture

Separate table for RL pipeline, not polluting the audit log:

```sql
CREATE TABLE rl_training_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What are we training?
    signal_type TEXT NOT NULL,  -- 'interpretation', 'synthesis'

    -- Input/output pair
    input_context JSONB NOT NULL,
    output_response JSONB NOT NULL,

    -- Reward signals (sparse)
    automated_score FLOAT,
    automated_dimensions JSONB,  -- {causal_depth, specificity, actionability}
    human_feedback_score FLOAT,  -- From thumbs up/down
    outcome_score FLOAT,  -- Did the fix work?

    -- Composite reward (computed by RL pipeline)
    computed_reward FLOAT,
    reward_computed_at TIMESTAMPTZ,

    -- Linkage
    investigation_id UUID NOT NULL REFERENCES investigations(id),
    source_event_id UUID REFERENCES investigation_feedback_events(id),

    -- Metadata
    model_version TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- For RL batch queries
    is_used_for_training BOOLEAN DEFAULT FALSE,
    training_batch_id UUID
);

CREATE INDEX idx_rl_signals_training
    ON rl_training_signals(signal_type, is_used_for_training, created_at);
```

### Signal Flow

1. **Automated (immediate):** Validator writes `automated_score` + `automated_dimensions`
2. **Human feedback (async):** User thumbs up/down updates `human_feedback_score`
3. **Outcome (async):** Batch job computes `outcome_score` based on:
   - Was there a follow-up investigation on same dataset?
   - Did user confirm fix worked?
   - Did anomaly recur?

## Retry Flow

When validation fails, retry with targeted hint based on `lowest_dimension`:

```python
async def _validate_and_retry(self, response, stage, retry_fn):
    for attempt in range(max_retries + 1):
        result = await validator.validate(response, context)

        if result.passed:
            return response

        if attempt < max_retries:
            hint = result.assessment.improvement_suggestion
            response = await retry_fn(hint)

    return response  # Best effort
```

Hint examples:
- `causal_depth`: "Your causal_chain needs intermediate steps between cause and symptom."
- `specificity`: "Include specific data: timestamps, row counts, table names."
- `actionability`: "Provide exact commands or steps, not generic advice."

## File Structure

```
backend/src/dataing/
├── core/
│   └── quality/
│       ├── __init__.py
│       ├── protocol.py          # QualityValidator protocol
│       ├── assessment.py        # QualityAssessment, ValidationResult
│       └── judge.py             # LLMJudgeValidator implementation
├── adapters/
│   ├── llm/
│   │   ├── client.py            # Updated prompts for new fields
│   │   └── response_models.py   # Updated with causal_chain, etc.
│   └── training/
│       ├── __init__.py
│       ├── repository.py        # TrainingSignalRepository
│       └── types.py             # TrainingSignal dataclass
```

## Implementation Steps

### Phase 1: Response Models
1. Update `response_models.py` with new required fields
2. Update prompts in `client.py` to guide LLM on new fields
3. Run tests, fix any structural validation issues

### Phase 2: Quality Validator
4. Create `core/quality/` module with protocol and assessment types
5. Implement `LLMJudgeValidator` with dimensional scoring
6. Write unit tests with mocked judge responses

### Phase 3: Training Signal Capture
7. Create `rl_training_signals` table migration
8. Implement `TrainingSignalRepository`
9. Wire up to existing `InvestigationFeedbackAdapter` for human feedback updates

### Phase 4: Orchestrator Integration
10. Add validator to orchestrator constructor
11. Implement `_validate_and_retry` for interpretation and synthesis
12. Add training signal capture calls

### Phase 5: Verification
13. Run full investigation flow end-to-end
14. Verify training signals are captured correctly
15. Test retry flow with intentionally low-quality responses

## Success Criteria

- [ ] Shallow interpretations ("confirms the issue exists") get rejected and retried
- [ ] Synthesis outputs include explicit causal chains with timing
- [ ] Recommendations are specific (commands, not "investigate")
- [ ] Training signals capture dimensional scores for all validated outputs
- [ ] Human feedback flows to `rl_training_signals.human_feedback_score`
- [ ] ~30% cost overhead (acceptable for quality improvement)
