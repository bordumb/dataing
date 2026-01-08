# Quality Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add LLM-as-judge quality validation to interpretation and synthesis stages, capturing training signals for future RL pipeline.

**Architecture:** Hexagonal design with QualityValidator protocol as port, LLMJudgeValidator as initial adapter. Separate rl_training_signals table for ML pipeline data capture.

**Tech Stack:** Pydantic AI, PostgreSQL, pytest-asyncio

---

## Phase 1: Response Models

### Task 1.1: Add Structured Fields to InterpretationResponse

**Files:**
- Modify: `backend/src/dataing/adapters/llm/response_models.py:113-133`
- Test: `backend/tests/unit/adapters/llm/test_response_models.py` (create)

**Step 1: Write the failing test**

Create `backend/tests/unit/adapters/llm/__init__.py`:
```python
"""Tests for LLM adapters."""
```

Create `backend/tests/unit/adapters/llm/test_response_models.py`:
```python
"""Tests for LLM response models."""

import pytest
from pydantic import ValidationError

from dataing.adapters.llm.response_models import InterpretationResponse


class TestInterpretationResponse:
    """Tests for InterpretationResponse model."""

    def test_valid_interpretation_with_causal_chain(self) -> None:
        """Test that valid interpretation with causal_chain passes validation."""
        response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.85,
            interpretation="The 485 orphaned orders appeared after 03:14 UTC when the users table stopped updating.",
            causal_chain="users ETL stopped at 03:14 -> stale table -> JOIN produces NULLs",
            key_findings=["485 orders with NULL user_id", "All created after 03:14 UTC"],
            next_investigation_step=None,
        )
        assert response.confidence == 0.85
        assert response.causal_chain is not None

    def test_causal_chain_required(self) -> None:
        """Test that causal_chain is required."""
        with pytest.raises(ValidationError) as exc_info:
            InterpretationResponse(
                supports_hypothesis=True,
                confidence=0.85,
                interpretation="The results confirm there are NULL user_ids in the orders table.",
                key_findings=["NULLs exist"],
            )
        assert "causal_chain" in str(exc_info.value)

    def test_causal_chain_min_length(self) -> None:
        """Test causal_chain minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            InterpretationResponse(
                supports_hypothesis=True,
                confidence=0.85,
                interpretation="The 485 orphaned orders appeared after 03:14 UTC when the users table stopped.",
                causal_chain="too short",
                key_findings=["485 orders affected"],
            )
        assert "causal_chain" in str(exc_info.value).lower()

    def test_key_findings_min_length(self) -> None:
        """Test key_findings requires at least 1 item."""
        with pytest.raises(ValidationError) as exc_info:
            InterpretationResponse(
                supports_hypothesis=True,
                confidence=0.85,
                interpretation="The 485 orphaned orders appeared after 03:14 UTC when the users table stopped.",
                causal_chain="users ETL stopped at 03:14 -> stale table -> JOIN produces NULLs",
                key_findings=[],
            )
        assert "key_findings" in str(exc_info.value).lower()

    def test_inconclusive_requires_next_step(self) -> None:
        """Test that inconclusive interpretation requires next_investigation_step."""
        # When supports_hypothesis is None (inconclusive), next_investigation_step should be provided
        # This is a soft requirement enforced by the LLM-as-judge, not Pydantic validation
        response = InterpretationResponse(
            supports_hypothesis=None,
            confidence=0.4,
            interpretation="The results are inconclusive - need more data to determine root cause.",
            causal_chain="Insufficient data to establish causal relationship",
            key_findings=["Query returned 0 rows"],
            next_investigation_step="Query the upstream users table directly",
        )
        assert response.next_investigation_step is not None
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/adapters/llm/test_response_models.py -v
```

Expected: FAIL with `causal_chain` field not found

**Step 3: Update InterpretationResponse with new fields**

Edit `backend/src/dataing/adapters/llm/response_models.py`, replace InterpretationResponse class:

```python
class InterpretationResponse(BaseModel):
    """LLM interpretation of query results.

    The causal_chain field forces the LLM to articulate cause-and-effect,
    not just confirm that an issue exists.
    """

    supports_hypothesis: bool | None = Field(
        description="True if evidence supports, False if refutes, None if inconclusive"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 (no confidence) to 1.0 (certain)",
    )
    interpretation: str = Field(
        description="What the results reveal about the ROOT CAUSE, not just the symptom",
        min_length=50,
    )
    causal_chain: str = Field(
        description=(
            "The cause-and-effect explanation: what upstream change led to this observation? "
            "Example: 'users ETL stopped at 03:14 -> stale table -> JOIN produces NULLs'"
        ),
        min_length=30,
    )
    key_findings: list[str] = Field(
        description="Specific findings with data points (counts, timestamps, table names)",
        min_length=1,
        max_length=5,
    )
    next_investigation_step: str | None = Field(
        default=None,
        description="If inconclusive: what query or check would help determine the root cause?",
    )
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/adapters/llm/test_response_models.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/tests/unit/adapters/llm/ backend/src/dataing/adapters/llm/response_models.py && git commit -m "feat(llm): add causal_chain to InterpretationResponse

Forces LLM to articulate cause-and-effect reasoning instead of
just confirming symptoms exist.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.2: Add Structured Fields to SynthesisResponse

**Files:**
- Modify: `backend/src/dataing/adapters/llm/response_models.py:135-163`
- Test: `backend/tests/unit/adapters/llm/test_response_models.py`

**Step 1: Add tests for SynthesisResponse**

Append to `backend/tests/unit/adapters/llm/test_response_models.py`:

```python
from dataing.adapters.llm.response_models import SynthesisResponse


class TestSynthesisResponse:
    """Tests for SynthesisResponse model."""

    def test_valid_synthesis_with_all_fields(self) -> None:
        """Test valid synthesis with all required fields."""
        response = SynthesisResponse(
            root_cause="Users ETL job timed out at 03:14 UTC due to API rate limiting",
            confidence=0.85,
            causal_chain=[
                "API rate limit hit at 03:14 UTC",
                "users ETL job timeout",
                "users table stale after 03:14",
                "orders JOIN produces NULLs",
            ],
            estimated_onset="03:14 UTC",
            affected_scope="orders table, order_items table, all downstream reports",
            supporting_evidence=["485 orders with NULL user_id", "Last user update: 03:14 UTC"],
            recommendations=["Re-run stg_users job: airflow trigger_dag stg_users --backfill"],
        )
        assert response.confidence == 0.85
        assert len(response.causal_chain) == 4

    def test_causal_chain_required(self) -> None:
        """Test that causal_chain is required."""
        with pytest.raises(ValidationError) as exc_info:
            SynthesisResponse(
                root_cause="Some root cause explanation here",
                confidence=0.85,
                estimated_onset="03:14 UTC",
                affected_scope="orders table and downstream",
                supporting_evidence=["evidence"],
                recommendations=["fix it"],
            )
        assert "causal_chain" in str(exc_info.value)

    def test_causal_chain_min_length(self) -> None:
        """Test causal_chain requires at least 2 steps."""
        with pytest.raises(ValidationError) as exc_info:
            SynthesisResponse(
                root_cause="Users ETL job timed out at 03:14 UTC",
                confidence=0.85,
                causal_chain=["only one step"],
                estimated_onset="03:14 UTC",
                affected_scope="orders table and downstream",
                supporting_evidence=["evidence"],
                recommendations=["fix it"],
            )
        assert "causal_chain" in str(exc_info.value).lower()

    def test_estimated_onset_required(self) -> None:
        """Test that estimated_onset is required."""
        with pytest.raises(ValidationError) as exc_info:
            SynthesisResponse(
                root_cause="Users ETL job timed out due to API rate limiting",
                confidence=0.85,
                causal_chain=["cause", "effect"],
                affected_scope="orders table and downstream",
                supporting_evidence=["evidence"],
                recommendations=["fix it"],
            )
        assert "estimated_onset" in str(exc_info.value)

    def test_affected_scope_required(self) -> None:
        """Test that affected_scope is required."""
        with pytest.raises(ValidationError) as exc_info:
            SynthesisResponse(
                root_cause="Users ETL job timed out due to API rate limiting",
                confidence=0.85,
                causal_chain=["cause", "effect"],
                estimated_onset="03:14 UTC",
                supporting_evidence=["evidence"],
                recommendations=["fix it"],
            )
        assert "affected_scope" in str(exc_info.value)

    def test_null_root_cause_allowed(self) -> None:
        """Test that null root_cause is allowed for inconclusive investigations."""
        response = SynthesisResponse(
            root_cause=None,
            confidence=0.3,
            causal_chain=["insufficient data", "cannot determine cause"],
            estimated_onset="unknown",
            affected_scope="unknown scope - need more investigation",
            supporting_evidence=["No clear evidence found"],
            recommendations=["Gather more data from upstream systems"],
        )
        assert response.root_cause is None
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/adapters/llm/test_response_models.py::TestSynthesisResponse -v
```

Expected: FAIL with `causal_chain` field not found

**Step 3: Update SynthesisResponse with new fields**

Edit `backend/src/dataing/adapters/llm/response_models.py`, replace SynthesisResponse class:

```python
class SynthesisResponse(BaseModel):
    """Final synthesis of investigation findings.

    Requires structured causal chain and impact assessment,
    not just a root cause string.
    """

    root_cause: str | None = Field(
        description=(
            "The UPSTREAM cause, not the symptom. Must explain WHY. "
            "Example: 'users ETL job timed out at 03:14 UTC due to API rate limiting' "
            "NOT: 'NULL user_ids in orders table'"
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in root cause (0.9+=certain, 0.7-0.9=likely, <0.7=uncertain)",
    )
    causal_chain: list[str] = Field(
        description=(
            "Step-by-step from root cause to observed symptom. "
            "Example: ['API rate limit hit', 'users ETL job timeout', "
            "'users table stale after 03:14', 'orders JOIN produces NULLs']"
        ),
        min_length=2,
        max_length=6,
    )
    estimated_onset: str = Field(
        description="When the issue started (timestamp or relative time, e.g., '03:14 UTC')",
        min_length=5,
    )
    affected_scope: str = Field(
        description="Blast radius: what else is affected? (downstream tables, reports, consumers)",
        min_length=10,
    )
    supporting_evidence: list[str] = Field(
        description="Specific evidence with data points that supports this conclusion",
        min_length=1,
        max_length=10,
    )
    recommendations: list[str] = Field(
        description=(
            "Actionable recommendations with specific targets. "
            "Example: 'Re-run stg_users job: airflow trigger_dag stg_users --backfill' "
            "NOT: 'Investigate the issue'"
        ),
        min_length=1,
        max_length=5,
    )

    @field_validator("root_cause")
    @classmethod
    def validate_root_cause_quality(cls, v: str | None) -> str | None:
        """Ensure root cause is specific enough."""
        if v is not None and len(v) < 20:
            raise ValueError("Root cause description too vague (min 20 chars)")
        return v
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/adapters/llm/test_response_models.py::TestSynthesisResponse -v
```

Expected: PASS

**Step 5: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/adapters/llm/response_models.py backend/tests/unit/adapters/llm/test_response_models.py && git commit -m "feat(llm): add causal_chain and impact fields to SynthesisResponse

Adds:
- causal_chain: step-by-step cause-effect path
- estimated_onset: when the issue started
- affected_scope: blast radius

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.3: Add Testability Fields to HypothesisResponse

**Files:**
- Modify: `backend/src/dataing/adapters/llm/response_models.py:19-72`
- Test: `backend/tests/unit/adapters/llm/test_response_models.py`

**Step 1: Add tests for HypothesisResponse**

Append to `backend/tests/unit/adapters/llm/test_response_models.py`:

```python
from dataing.adapters.llm.response_models import HypothesisResponse
from dataing.core.domain_types import HypothesisCategory


class TestHypothesisResponse:
    """Tests for HypothesisResponse model."""

    def test_valid_hypothesis_with_testability_fields(self) -> None:
        """Test valid hypothesis with expected_if_true/false fields."""
        response = HypothesisResponse(
            id="h1",
            title="Upstream users ETL job failed causing NULL user_ids",
            category=HypothesisCategory.UPSTREAM_DEPENDENCY,
            reasoning="The users table may have stopped receiving updates, causing JOINs to fail",
            suggested_query="SELECT COUNT(*) FROM orders WHERE user_id IS NULL LIMIT 100",
            expected_if_true="High count of NULL user_ids after a specific timestamp",
            expected_if_false="Zero or very few NULL user_ids",
        )
        assert response.expected_if_true is not None
        assert response.expected_if_false is not None

    def test_expected_if_true_required(self) -> None:
        """Test that expected_if_true is required."""
        with pytest.raises(ValidationError) as exc_info:
            HypothesisResponse(
                id="h1",
                title="Upstream users ETL job failed",
                category=HypothesisCategory.UPSTREAM_DEPENDENCY,
                reasoning="The users table may have stopped receiving updates",
                suggested_query="SELECT COUNT(*) FROM orders WHERE user_id IS NULL LIMIT 100",
                expected_if_false="Zero NULL user_ids",
            )
        assert "expected_if_true" in str(exc_info.value)

    def test_expected_if_false_required(self) -> None:
        """Test that expected_if_false is required."""
        with pytest.raises(ValidationError) as exc_info:
            HypothesisResponse(
                id="h1",
                title="Upstream users ETL job failed",
                category=HypothesisCategory.UPSTREAM_DEPENDENCY,
                reasoning="The users table may have stopped receiving updates",
                suggested_query="SELECT COUNT(*) FROM orders WHERE user_id IS NULL LIMIT 100",
                expected_if_true="High count of NULL user_ids",
            )
        assert "expected_if_false" in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/adapters/llm/test_response_models.py::TestHypothesisResponse -v
```

Expected: FAIL with `expected_if_true` field not found

**Step 3: Update HypothesisResponse with new fields**

Edit `backend/src/dataing/adapters/llm/response_models.py`, update HypothesisResponse class to add fields after `suggested_query`:

```python
class HypothesisResponse(BaseModel):
    """Single hypothesis from the LLM."""

    id: str = Field(description="Unique identifier like 'h1', 'h2', etc.")
    title: str = Field(
        description="Short, specific title describing the potential cause",
        min_length=10,
        max_length=200,
    )
    category: HypothesisCategory = Field(description="Classification of the hypothesis type")
    reasoning: str = Field(
        description="Explanation of why this could be the cause",
        min_length=20,
    )
    suggested_query: str = Field(
        description="SQL query to investigate this hypothesis. Must include LIMIT clause.",
    )
    expected_if_true: str = Field(
        description="What results we expect if this hypothesis is correct",
        min_length=10,
    )
    expected_if_false: str = Field(
        description="What results we expect if this hypothesis is wrong",
        min_length=10,
    )

    @field_validator("suggested_query")
    @classmethod
    def validate_query_safety(cls, v: str) -> str:
        """Validate query safety: strip markdown, require LIMIT, block mutations."""
        # Strip markdown if present
        if v.startswith("```"):
            lines = v.strip().split("\n")
            v = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        upper_query = v.upper().strip()

        # Ensure query has LIMIT clause for safety
        if "LIMIT" not in upper_query:
            raise ValueError("Query must include LIMIT clause")

        # Ensure query is read-only using word boundary regex to avoid false positives
        dangerous = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "TRUNCATE",
            "ALTER",
            "CREATE",
            "MERGE",
            "GRANT",
            "REVOKE",
            "EXEC",
            "EXECUTE",
        ]
        pattern = r"\b(" + "|".join(dangerous) + r")\b"
        if re.search(pattern, upper_query):
            raise ValueError("Query contains forbidden SQL operation")

        return v.strip()
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/adapters/llm/test_response_models.py::TestHypothesisResponse -v
```

Expected: PASS

**Step 5: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/adapters/llm/response_models.py backend/tests/unit/adapters/llm/test_response_models.py && git commit -m "feat(llm): add testability fields to HypothesisResponse

Adds expected_if_true and expected_if_false to make hypotheses
explicitly testable.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.4: Update LLM Client Prompts for New Fields

**Files:**
- Modify: `backend/src/dataing/adapters/llm/client.py`

**Step 1: Run existing tests to establish baseline**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit -k "llm or orchestrator" -v --tb=short 2>&1 | tail -20
```

**Step 2: Update interpretation system prompt**

Edit `backend/src/dataing/adapters/llm/client.py`, update `_build_interpretation_system_prompt` method:

```python
def _build_interpretation_system_prompt(self) -> str:
    """Build system prompt for evidence interpretation."""
    return """You are analyzing query results to determine ROOT CAUSE, not just confirm symptoms.

CRITICAL - Understanding "supports hypothesis":
- If investigating NULLs and query FINDS NULLs -> supports=true (we found the problem)
- If investigating NULLs and query finds NO NULLs -> supports=false (not the cause)
- "Supports" means evidence helps explain the anomaly, NOT that the situation is good

Your interpretation MUST:
1. Explain the CAUSAL CHAIN: what upstream change led to this observation?
2. Include SPECIFIC DATA: timestamps, counts, table/column names from the results
3. If inconclusive, suggest the NEXT INVESTIGATION STEP

BAD (confirms symptom without explaining cause):
"The query results confirm there are NULL user_ids in the orders table."

GOOD (explains causal chain with specifics):
"The 485 NULL user_ids all appeared after 03:14 UTC. The users table shows no
updates since 03:14 UTC, suggesting the upstream ETL job stopped. This temporal
correlation indicates the users ETL failure caused the JOIN to produce NULLs."

Provide:
1. supports_hypothesis: true/false/null based on evidence
2. confidence: 0.0-1.0
3. interpretation: explanation of what results reveal (min 50 chars)
4. causal_chain: the cause-effect relationship (min 30 chars)
5. key_findings: 1-5 specific data points from the results
6. next_investigation_step: required if inconclusive"""
```

**Step 3: Update synthesis system prompt**

Edit `backend/src/dataing/adapters/llm/client.py`, update `_build_synthesis_system_prompt` method:

```python
def _build_synthesis_system_prompt(self) -> str:
    """Build system prompt for synthesis."""
    return """You are synthesizing investigation findings into a ROOT CAUSE determination.

Your synthesis MUST:
1. Identify the UPSTREAM cause, not the symptom
2. Provide a CAUSAL CHAIN from root cause to observed anomaly
3. Estimate WHEN the issue started
4. Describe WHAT ELSE is affected (blast radius)
5. Give SPECIFIC, ACTIONABLE recommendations

ROOT CAUSE vs SYMPTOM:
- SYMPTOM: "NULL user_ids in orders table" (what we observe)
- ROOT CAUSE: "users ETL job timeout at 03:14 UTC caused by API rate limit" (why it happened)

CONFIDENCE CALIBRATION:
- 0.9+: Direct evidence of the cause (job failure logs, schema change)
- 0.7-0.9: Strong circumstantial evidence with clear causal chain
- 0.5-0.7: Plausible explanation but alternatives possible
- <0.5: Inconclusive (set root_cause to null)

ACTIONABLE RECOMMENDATIONS:
- BAD: "Investigate the issue", "Check the data"
- GOOD: "Re-run stg_users job: airflow trigger_dag stg_users --backfill"
- GOOD: "Check CloudWatch logs for stg_users job at 03:14 UTC"

Provide:
1. root_cause: upstream cause (min 20 chars, or null if inconclusive)
2. confidence: 0.0-1.0 calibrated per guidelines above
3. causal_chain: 2-6 steps from cause to symptom
4. estimated_onset: when the issue started
5. affected_scope: blast radius (min 10 chars)
6. supporting_evidence: 1-10 specific data points
7. recommendations: 1-5 actionable items with specific targets"""
```

**Step 4: Update hypothesis system prompt**

Edit `backend/src/dataing/adapters/llm/client.py`, update `_build_hypothesis_system_prompt` method to include testability:

```python
def _build_hypothesis_system_prompt(self, num_hypotheses: int) -> str:
    """Build system prompt for hypothesis generation."""
    return f"""You are a data quality investigator. Given an anomaly alert and database context,
generate {num_hypotheses} hypotheses about what could have caused the anomaly.

CRITICAL: Pay close attention to the METRIC NAME in the alert:
- "null_count": Investigate what causes NULL values (app bugs, missing required fields, ETL drops)
- "row_count" or "volume": Investigate missing/extra records (filtering bugs, data loss, duplicates)
- "duplicate_count": Investigate what causes duplicate records
- Other metrics: Investigate value changes, data corruption, calculation errors

HYPOTHESIS CATEGORIES:
- upstream_dependency: Source table missing data, late arrival, schema change
- transformation_bug: ETL logic error, incorrect aggregation, wrong join
- data_quality: Nulls, duplicates, invalid values, schema drift
- infrastructure: Job failure, timeout, resource exhaustion
- expected_variance: Seasonality, holiday, known business event

Each hypothesis MUST:
1. DIRECTLY address the specific metric in the alert
2. Have a clear, specific title (10-200 characters)
3. Include reasoning for why this could be the cause (at least 20 characters)
4. Suggest a SQL query to investigate using ONLY provided schema tables
5. Include LIMIT clause in all queries
6. Use only SELECT statements (no mutations)
7. Specify expected_if_true: what results confirm this hypothesis
8. Specify expected_if_false: what results refute this hypothesis

Generate diverse hypotheses covering multiple categories when plausible."""
```

**Step 5: Run lint and type check**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run ruff check src/dataing/adapters/llm/client.py && uv run mypy src/dataing/adapters/llm/client.py
```

**Step 6: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/adapters/llm/client.py && git commit -m "feat(llm): update prompts for structured causal reasoning

Updates system prompts to guide LLM on:
- causal_chain requirements
- estimated_onset and affected_scope
- testability criteria for hypotheses
- actionable recommendation examples

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: Quality Validator

### Task 2.1: Create Quality Assessment Types

**Files:**
- Create: `backend/src/dataing/core/quality/__init__.py`
- Create: `backend/src/dataing/core/quality/assessment.py`
- Test: `backend/tests/unit/core/quality/test_assessment.py`

**Step 1: Create the directory and __init__.py**

Create `backend/src/dataing/core/quality/__init__.py`:
```python
"""Quality validation module for LLM outputs."""

from .assessment import QualityAssessment, ValidationResult

__all__ = ["QualityAssessment", "ValidationResult"]
```

**Step 2: Write the failing test**

Create `backend/tests/unit/core/quality/__init__.py`:
```python
"""Tests for quality validation module."""
```

Create `backend/tests/unit/core/quality/test_assessment.py`:
```python
"""Tests for quality assessment types."""

import pytest

from dataing.core.quality.assessment import QualityAssessment, ValidationResult


class TestQualityAssessment:
    """Tests for QualityAssessment model."""

    def test_composite_score_calculation(self) -> None:
        """Test weighted composite score calculation."""
        assessment = QualityAssessment(
            causal_depth=0.8,
            specificity=0.6,
            actionability=0.4,
            lowest_dimension="actionability",
            improvement_suggestion="Provide specific commands instead of generic advice",
        )
        # 0.8 * 0.5 + 0.6 * 0.3 + 0.4 * 0.2 = 0.4 + 0.18 + 0.08 = 0.66
        assert assessment.composite_score == pytest.approx(0.66)

    def test_composite_score_all_high(self) -> None:
        """Test composite score when all dimensions are high."""
        assessment = QualityAssessment(
            causal_depth=0.9,
            specificity=0.9,
            actionability=0.9,
            lowest_dimension="causal_depth",
            improvement_suggestion="Minor improvements possible",
        )
        # 0.9 * 0.5 + 0.9 * 0.3 + 0.9 * 0.2 = 0.45 + 0.27 + 0.18 = 0.9
        assert assessment.composite_score == pytest.approx(0.9)

    def test_score_bounds(self) -> None:
        """Test that scores must be between 0 and 1."""
        with pytest.raises(ValueError):
            QualityAssessment(
                causal_depth=1.5,  # Invalid
                specificity=0.5,
                actionability=0.5,
                lowest_dimension="causal_depth",
                improvement_suggestion="Test",
            )


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_training_signals_property(self) -> None:
        """Test training_signals computed property."""
        assessment = QualityAssessment(
            causal_depth=0.7,
            specificity=0.8,
            actionability=0.5,
            lowest_dimension="actionability",
            improvement_suggestion="Be more specific about actions",
        )
        result = ValidationResult(passed=True, assessment=assessment)

        signals = result.training_signals
        assert signals["causal_depth"] == 0.7
        assert signals["specificity"] == 0.8
        assert signals["actionability"] == 0.5
        assert "composite" in signals

    def test_passed_based_on_threshold(self) -> None:
        """Test that passed reflects composite score vs threshold."""
        assessment = QualityAssessment(
            causal_depth=0.8,
            specificity=0.7,
            actionability=0.6,
            lowest_dimension="actionability",
            improvement_suggestion="Minor improvements",
        )
        # composite = 0.8*0.5 + 0.7*0.3 + 0.6*0.2 = 0.4 + 0.21 + 0.12 = 0.73
        result = ValidationResult(passed=True, assessment=assessment)
        assert result.passed is True
        assert result.assessment.composite_score == pytest.approx(0.73)
```

**Step 3: Run test to verify it fails**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/core/quality/test_assessment.py -v
```

Expected: FAIL with module not found

**Step 4: Implement assessment types**

Create `backend/src/dataing/core/quality/assessment.py`:
```python
"""Quality assessment types for LLM output validation."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class QualityAssessment(BaseModel):
    """Dimensional quality scores from LLM-as-judge.

    Attributes:
        causal_depth: Score for causal reasoning quality (0-1).
        specificity: Score for concrete data points (0-1).
        actionability: Score for actionable recommendations (0-1).
        lowest_dimension: Which dimension scored lowest.
        improvement_suggestion: How to improve the lowest dimension.
    """

    causal_depth: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Does causal_chain explain WHY? "
            "0=restates symptom, 0.5=cause without mechanism, 1=full causal chain"
        ),
    )
    specificity: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Are there concrete data points? "
            "0=vague, 0.5=some numbers, 1=timestamps+counts+names"
        ),
    )
    actionability: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Can someone act on recommendations? "
            "0=generic advice, 0.5=direction without specifics, 1=exact commands/steps"
        ),
    )
    lowest_dimension: str = Field(
        description="Which dimension scored lowest: 'causal_depth', 'specificity', or 'actionability'"
    )
    improvement_suggestion: str = Field(
        min_length=20,
        description="Specific suggestion to improve the lowest-scoring dimension",
    )

    @computed_field
    @property
    def composite_score(self) -> float:
        """Calculate weighted composite score for pass/fail decisions."""
        return self.causal_depth * 0.5 + self.specificity * 0.3 + self.actionability * 0.2


class ValidationResult(BaseModel):
    """Result of quality validation.

    Attributes:
        passed: Whether the response passed validation.
        assessment: Detailed quality assessment with dimensional scores.
    """

    passed: bool
    assessment: QualityAssessment

    @computed_field
    @property
    def training_signals(self) -> dict[str, float]:
        """Extract dimensional scores for RL training."""
        return {
            "causal_depth": self.assessment.causal_depth,
            "specificity": self.assessment.specificity,
            "actionability": self.assessment.actionability,
            "composite": self.assessment.composite_score,
        }
```

**Step 5: Run test to verify it passes**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/core/quality/test_assessment.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/core/quality/ backend/tests/unit/core/quality/ && git commit -m "feat(quality): add QualityAssessment and ValidationResult types

Implements dimensional quality scoring:
- causal_depth (50% weight)
- specificity (30% weight)
- actionability (20% weight)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2.2: Create QualityValidator Protocol

**Files:**
- Create: `backend/src/dataing/core/quality/protocol.py`
- Update: `backend/src/dataing/core/quality/__init__.py`

**Step 1: Create the protocol**

Create `backend/src/dataing/core/quality/protocol.py`:
```python
"""Protocol definition for quality validators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dataing.adapters.llm.response_models import (
        InterpretationResponse,
        SynthesisResponse,
    )

    from .assessment import ValidationResult


@runtime_checkable
class QualityValidator(Protocol):
    """Interface for LLM output quality validation.

    Implementations may use:
    - LLM-as-judge (semantic validation)
    - Regex patterns (rule-based validation)
    - RL-based scoring (learned validation)

    All implementations return dimensional quality scores
    for training signal capture.
    """

    async def validate_interpretation(
        self,
        response: InterpretationResponse,
        hypothesis_title: str,
        query: str,
    ) -> ValidationResult:
        """Validate an interpretation response.

        Args:
            response: The interpretation to validate.
            hypothesis_title: Title of the hypothesis being tested.
            query: The SQL query that was executed.

        Returns:
            ValidationResult with pass/fail and dimensional scores.
        """
        ...

    async def validate_synthesis(
        self,
        response: SynthesisResponse,
        alert_summary: str,
    ) -> ValidationResult:
        """Validate a synthesis response.

        Args:
            response: The synthesis to validate.
            alert_summary: Summary of the original anomaly alert.

        Returns:
            ValidationResult with pass/fail and dimensional scores.
        """
        ...
```

**Step 2: Update __init__.py**

Update `backend/src/dataing/core/quality/__init__.py`:
```python
"""Quality validation module for LLM outputs."""

from .assessment import QualityAssessment, ValidationResult
from .protocol import QualityValidator

__all__ = ["QualityAssessment", "QualityValidator", "ValidationResult"]
```

**Step 3: Run type check**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run mypy src/dataing/core/quality/
```

**Step 4: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/core/quality/ && git commit -m "feat(quality): add QualityValidator protocol

Hexagonal port for quality validation with swappable adapters
(LLM-judge, regex, RL-based).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2.3: Implement LLMJudgeValidator

**Files:**
- Create: `backend/src/dataing/core/quality/judge.py`
- Test: `backend/tests/unit/core/quality/test_judge.py`

**Step 1: Write the failing test**

Create `backend/tests/unit/core/quality/test_judge.py`:
```python
"""Tests for LLM-as-judge quality validator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dataing.adapters.llm.response_models import InterpretationResponse, SynthesisResponse
from dataing.core.quality.assessment import QualityAssessment
from dataing.core.quality.judge import LLMJudgeValidator


class TestLLMJudgeValidator:
    """Tests for LLMJudgeValidator."""

    @pytest.fixture
    def mock_judge_agent(self) -> MagicMock:
        """Create a mock judge agent."""
        agent = MagicMock()
        agent.run = AsyncMock()
        return agent

    @pytest.fixture
    def validator(self, mock_judge_agent: MagicMock) -> LLMJudgeValidator:
        """Create validator with mocked agent."""
        validator = LLMJudgeValidator.__new__(LLMJudgeValidator)
        validator.pass_threshold = 0.6
        validator.judge = mock_judge_agent
        return validator

    @pytest.mark.asyncio
    async def test_validate_interpretation_passes(
        self, validator: LLMJudgeValidator, mock_judge_agent: MagicMock
    ) -> None:
        """Test interpretation validation passes when score is above threshold."""
        mock_judge_agent.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.8,
                specificity=0.7,
                actionability=0.6,
                lowest_dimension="actionability",
                improvement_suggestion="Could include more specific action items",
            )
        )

        response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.85,
            interpretation="The 485 orphaned orders appeared after 03:14 UTC when users table stopped.",
            causal_chain="users ETL stopped -> stale table -> JOIN NULLs",
            key_findings=["485 orders affected"],
        )

        result = await validator.validate_interpretation(
            response=response,
            hypothesis_title="Users ETL failure",
            query="SELECT * FROM orders WHERE user_id IS NULL LIMIT 100",
        )

        assert result.passed is True
        assert result.assessment.causal_depth == 0.8

    @pytest.mark.asyncio
    async def test_validate_interpretation_fails(
        self, validator: LLMJudgeValidator, mock_judge_agent: MagicMock
    ) -> None:
        """Test interpretation validation fails when score is below threshold."""
        mock_judge_agent.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.3,
                specificity=0.4,
                actionability=0.2,
                lowest_dimension="causal_depth",
                improvement_suggestion="Explain the causal chain from cause to effect",
            )
        )

        response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.85,
            interpretation="The query confirms there are NULL values in the user_id column.",
            causal_chain="NULLs exist in the data",
            key_findings=["NULLs found"],
        )

        result = await validator.validate_interpretation(
            response=response,
            hypothesis_title="Users ETL failure",
            query="SELECT * FROM orders WHERE user_id IS NULL LIMIT 100",
        )

        assert result.passed is False
        assert result.assessment.lowest_dimension == "causal_depth"

    @pytest.mark.asyncio
    async def test_validate_synthesis_passes(
        self, validator: LLMJudgeValidator, mock_judge_agent: MagicMock
    ) -> None:
        """Test synthesis validation passes with good quality."""
        mock_judge_agent.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.9,
                specificity=0.8,
                actionability=0.7,
                lowest_dimension="actionability",
                improvement_suggestion="Could add exact command syntax",
            )
        )

        response = SynthesisResponse(
            root_cause="Users ETL job timed out at 03:14 UTC due to API rate limiting",
            confidence=0.85,
            causal_chain=["API rate limit", "ETL timeout", "stale table", "JOIN NULLs"],
            estimated_onset="03:14 UTC",
            affected_scope="orders table and downstream reports",
            supporting_evidence=["485 NULLs", "Last update 03:14"],
            recommendations=["Re-run stg_users with backfill"],
        )

        result = await validator.validate_synthesis(
            response=response,
            alert_summary="null_count on orders.user_id: expected 0, got 485",
        )

        assert result.passed is True
        assert result.assessment.composite_score > 0.6

    @pytest.mark.asyncio
    async def test_training_signals_captured(
        self, validator: LLMJudgeValidator, mock_judge_agent: MagicMock
    ) -> None:
        """Test that training signals are properly captured."""
        mock_judge_agent.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.7,
                specificity=0.6,
                actionability=0.5,
                lowest_dimension="actionability",
                improvement_suggestion="Add specific commands",
            )
        )

        response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.8,
            interpretation="The data shows a clear pattern of NULLs appearing after the ETL failure.",
            causal_chain="ETL failure -> missing data -> NULLs",
            key_findings=["Pattern detected"],
        )

        result = await validator.validate_interpretation(
            response=response,
            hypothesis_title="Test",
            query="SELECT 1 LIMIT 1",
        )

        signals = result.training_signals
        assert "causal_depth" in signals
        assert "specificity" in signals
        assert "actionability" in signals
        assert "composite" in signals
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/core/quality/test_judge.py -v
```

Expected: FAIL with module not found

**Step 3: Implement LLMJudgeValidator**

Create `backend/src/dataing/core/quality/judge.py`:
```python
"""LLM-as-judge quality validator implementation."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel

from .assessment import QualityAssessment, ValidationResult

if TYPE_CHECKING:
    from dataing.adapters.llm.response_models import (
        InterpretationResponse,
        SynthesisResponse,
    )


JUDGE_SYSTEM_PROMPT = """You evaluate root cause analysis quality on three dimensions.

## Causal Depth (50% weight)
Evaluate the causal_chain field:
- 0.0-0.2: Empty or just restates symptom ("NULLs exist")
- 0.3-0.4: Names a cause but no mechanism ("upstream issue")
- 0.5-0.6: Cause + effect but missing intermediate steps
- 0.7-0.8: Full chain but vague on timing/mechanism
- 0.9-1.0: Complete chain with timing ("ETL timeout at 03:14 -> stale table -> JOIN NULLs")

## Specificity (30% weight)
Evaluate key_findings and supporting_evidence:
- 0.0-0.2: No concrete data
- 0.3-0.4: Vague quantities ("many rows")
- 0.5-0.6: Some numbers but no timestamps
- 0.7-0.8: Numbers + timestamps OR entity names
- 0.9-1.0: Timestamps + counts + specific table/column names

## Actionability (20% weight)
Evaluate recommendations:
- 0.0-0.2: "Investigate the issue"
- 0.3-0.4: "Check the ETL job"
- 0.5-0.6: "Check the stg_users ETL job logs"
- 0.7-0.8: "Check CloudWatch for stg_users job failures around 03:14 UTC"
- 0.9-1.0: "Run: airflow trigger_dag stg_users --conf '{\\"backfill\\": true}'"

Be calibrated: most responses score 0.4-0.7. Reserve 0.9+ for exceptional quality.

Always identify the lowest_dimension and provide a specific improvement_suggestion
(at least 20 characters) that explains how to improve that dimension."""


class LLMJudgeValidator:
    """Quality validator using LLM-as-judge with dimensional scoring.

    Attributes:
        pass_threshold: Minimum composite score to pass validation.
        judge: Pydantic AI agent configured for quality assessment.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        pass_threshold: float = 0.6,
    ) -> None:
        """Initialize the LLM judge validator.

        Args:
            api_key: Anthropic API key.
            model: Model to use for judging.
            pass_threshold: Minimum composite score to pass (0.0-1.0).
        """
        os.environ["ANTHROPIC_API_KEY"] = api_key
        self.pass_threshold = pass_threshold
        self.judge: Agent[None, QualityAssessment] = Agent(
            model=AnthropicModel(model),
            output_type=QualityAssessment,
            system_prompt=JUDGE_SYSTEM_PROMPT,
        )

    async def validate_interpretation(
        self,
        response: InterpretationResponse,
        hypothesis_title: str,
        query: str,
    ) -> ValidationResult:
        """Validate an interpretation response.

        Args:
            response: The interpretation to validate.
            hypothesis_title: Title of the hypothesis being tested.
            query: The SQL query that was executed.

        Returns:
            ValidationResult with pass/fail and dimensional scores.
        """
        prompt = f"""Evaluate this interpretation:

HYPOTHESIS TESTED: {hypothesis_title}
QUERY RUN: {query}

RESPONSE:
- interpretation: {response.interpretation}
- causal_chain: {response.causal_chain}
- confidence: {response.confidence}
- key_findings: {response.key_findings}
- supports_hypothesis: {response.supports_hypothesis}

Score each dimension and identify what needs improvement."""

        result = await self.judge.run(prompt)

        return ValidationResult(
            passed=result.output.composite_score >= self.pass_threshold,
            assessment=result.output,
        )

    async def validate_synthesis(
        self,
        response: SynthesisResponse,
        alert_summary: str,
    ) -> ValidationResult:
        """Validate a synthesis response.

        Args:
            response: The synthesis to validate.
            alert_summary: Summary of the original anomaly alert.

        Returns:
            ValidationResult with pass/fail and dimensional scores.
        """
        causal_chain_str = " -> ".join(response.causal_chain)

        prompt = f"""Evaluate this root cause analysis:

ORIGINAL ANOMALY: {alert_summary}

RESPONSE:
- root_cause: {response.root_cause}
- confidence: {response.confidence}
- causal_chain: {causal_chain_str}
- estimated_onset: {response.estimated_onset}
- affected_scope: {response.affected_scope}
- supporting_evidence: {response.supporting_evidence}
- recommendations: {response.recommendations}

Score each dimension and identify what needs improvement."""

        result = await self.judge.run(prompt)

        return ValidationResult(
            passed=result.output.composite_score >= self.pass_threshold,
            assessment=result.output,
        )
```

**Step 4: Update __init__.py**

Update `backend/src/dataing/core/quality/__init__.py`:
```python
"""Quality validation module for LLM outputs."""

from .assessment import QualityAssessment, ValidationResult
from .judge import LLMJudgeValidator
from .protocol import QualityValidator

__all__ = ["LLMJudgeValidator", "QualityAssessment", "QualityValidator", "ValidationResult"]
```

**Step 5: Run test to verify it passes**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/core/quality/test_judge.py -v
```

Expected: PASS

**Step 6: Run lint and type check**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run ruff check src/dataing/core/quality/ && uv run mypy src/dataing/core/quality/
```

**Step 7: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/core/quality/ backend/tests/unit/core/quality/ && git commit -m "feat(quality): implement LLMJudgeValidator

LLM-as-judge validator with:
- Dimensional scoring (causal_depth, specificity, actionability)
- Calibrated rubric for consistent evaluation
- Improvement suggestions for retry hints

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 3: Training Signal Capture

### Task 3.1: Create RL Training Signals Migration

**Files:**
- Create: `backend/migrations/011_rl_training_signals.sql`

**Step 1: Create migration file**

Create `backend/migrations/011_rl_training_signals.sql`:
```sql
-- RL Training Signals table for ML pipeline
-- Captures input/output pairs with reward signals for future RL training

CREATE TABLE IF NOT EXISTS rl_training_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What are we training?
    signal_type TEXT NOT NULL,  -- 'interpretation', 'synthesis'

    -- Input/output pair
    input_context JSONB NOT NULL,
    output_response JSONB NOT NULL,

    -- Reward signals (sparse - not all will be present)
    automated_score FLOAT,
    automated_dimensions JSONB,  -- {causal_depth, specificity, actionability}
    human_feedback_score FLOAT,  -- From thumbs up/down (-1, 0, 1)
    outcome_score FLOAT,  -- Did the fix work?

    -- Composite reward (computed by RL pipeline, not at insert time)
    computed_reward FLOAT,
    reward_computed_at TIMESTAMPTZ,

    -- Linkage
    tenant_id UUID NOT NULL,
    investigation_id UUID NOT NULL,
    source_event_id UUID,

    -- Metadata
    model_version TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- For RL batch queries
    is_used_for_training BOOLEAN DEFAULT FALSE,
    training_batch_id UUID
);

-- Index for RL pipeline batch queries
CREATE INDEX IF NOT EXISTS idx_rl_signals_training
    ON rl_training_signals(signal_type, is_used_for_training, created_at);

-- Index for investigation lookups
CREATE INDEX IF NOT EXISTS idx_rl_signals_investigation
    ON rl_training_signals(investigation_id);

-- Index for tenant scoping
CREATE INDEX IF NOT EXISTS idx_rl_signals_tenant
    ON rl_training_signals(tenant_id);

COMMENT ON TABLE rl_training_signals IS 'Training signals for RL pipeline - captures LLM input/output pairs with reward signals';
COMMENT ON COLUMN rl_training_signals.signal_type IS 'Type of LLM output: interpretation or synthesis';
COMMENT ON COLUMN rl_training_signals.automated_score IS 'Composite score from LLM-as-judge (0.0-1.0)';
COMMENT ON COLUMN rl_training_signals.automated_dimensions IS 'Dimensional scores: {causal_depth, specificity, actionability}';
COMMENT ON COLUMN rl_training_signals.human_feedback_score IS 'User feedback: -1 (bad), 0 (neutral), 1 (good)';
COMMENT ON COLUMN rl_training_signals.outcome_score IS 'Did the root cause determination lead to a fix? (computed async)';
```

**Step 2: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/migrations/011_rl_training_signals.sql && git commit -m "feat(db): add rl_training_signals table

Captures LLM input/output pairs with reward signals for
future RL training pipeline:
- Automated scores from LLM-as-judge
- Human feedback scores
- Outcome scores (async)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 3.2: Create TrainingSignalRepository

**Files:**
- Create: `backend/src/dataing/adapters/training/__init__.py`
- Create: `backend/src/dataing/adapters/training/types.py`
- Create: `backend/src/dataing/adapters/training/repository.py`
- Test: `backend/tests/unit/adapters/training/test_repository.py`

**Step 1: Create the directory structure**

Create `backend/src/dataing/adapters/training/__init__.py`:
```python
"""Training signal adapters for RL pipeline."""

from .repository import TrainingSignalRepository
from .types import TrainingSignal

__all__ = ["TrainingSignal", "TrainingSignalRepository"]
```

Create `backend/src/dataing/adapters/training/types.py`:
```python
"""Types for training signal capture."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class TrainingSignal:
    """Training signal for RL pipeline.

    Attributes:
        id: Unique signal identifier.
        signal_type: Type of LLM output (interpretation, synthesis).
        tenant_id: Tenant this signal belongs to.
        investigation_id: Investigation this signal relates to.
        input_context: Context provided to the LLM.
        output_response: Response from the LLM.
        automated_score: Composite score from validator.
        automated_dimensions: Dimensional scores.
        model_version: Version of the model that produced the output.
        created_at: When the signal was created.
    """

    signal_type: str
    tenant_id: UUID
    investigation_id: UUID
    input_context: dict[str, Any]
    output_response: dict[str, Any]
    automated_score: float | None = None
    automated_dimensions: dict[str, float] | None = None
    model_version: str | None = None
    source_event_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

**Step 2: Write the failing test**

Create `backend/tests/unit/adapters/training/__init__.py`:
```python
"""Tests for training signal adapters."""
```

Create `backend/tests/unit/adapters/training/test_repository.py`:
```python
"""Tests for TrainingSignalRepository."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dataing.adapters.training.repository import TrainingSignalRepository
from dataing.adapters.training.types import TrainingSignal


class TestTrainingSignalRepository:
    """Tests for TrainingSignalRepository."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database."""
        db = MagicMock()
        db.execute = AsyncMock()
        db.fetch_one = AsyncMock()
        return db

    @pytest.fixture
    def repository(self, mock_db: MagicMock) -> TrainingSignalRepository:
        """Create repository with mock database."""
        return TrainingSignalRepository(db=mock_db)

    @pytest.mark.asyncio
    async def test_record_signal(
        self, repository: TrainingSignalRepository, mock_db: MagicMock
    ) -> None:
        """Test recording a training signal."""
        tenant_id = uuid4()
        investigation_id = uuid4()

        signal_id = await repository.record_signal(
            signal_type="interpretation",
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            input_context={"hypothesis": "test", "query": "SELECT 1"},
            output_response={"interpretation": "test result"},
            automated_score=0.75,
            automated_dimensions={"causal_depth": 0.8, "specificity": 0.7, "actionability": 0.6},
        )

        assert signal_id is not None
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_human_feedback(
        self, repository: TrainingSignalRepository, mock_db: MagicMock
    ) -> None:
        """Test updating human feedback score."""
        investigation_id = uuid4()

        await repository.update_human_feedback(
            investigation_id=investigation_id,
            signal_type="synthesis",
            score=1.0,
        )

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "human_feedback_score" in call_args[0][0]
```

**Step 3: Run test to verify it fails**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/adapters/training/test_repository.py -v
```

Expected: FAIL with module not found

**Step 4: Implement TrainingSignalRepository**

Create `backend/src/dataing/adapters/training/repository.py`:
```python
"""Repository for training signal persistence."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from .types import TrainingSignal

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()


class TrainingSignalRepository:
    """Repository for persisting training signals.

    Attributes:
        db: Application database for storing signals.
    """

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the repository.

        Args:
            db: Application database connection.
        """
        self.db = db

    async def record_signal(
        self,
        signal_type: str,
        tenant_id: UUID,
        investigation_id: UUID,
        input_context: dict[str, Any],
        output_response: dict[str, Any],
        automated_score: float | None = None,
        automated_dimensions: dict[str, float] | None = None,
        model_version: str | None = None,
        source_event_id: UUID | None = None,
    ) -> UUID:
        """Record a training signal.

        Args:
            signal_type: Type of output (interpretation, synthesis).
            tenant_id: Tenant identifier.
            investigation_id: Investigation identifier.
            input_context: Context provided to LLM.
            output_response: Response from LLM.
            automated_score: Composite score from validator.
            automated_dimensions: Dimensional scores.
            model_version: Model version string.
            source_event_id: Optional link to feedback event.

        Returns:
            UUID of the created signal.
        """
        signal_id = uuid4()

        query = """
            INSERT INTO rl_training_signals (
                id, signal_type, tenant_id, investigation_id,
                input_context, output_response,
                automated_score, automated_dimensions,
                model_version, source_event_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """

        await self.db.execute(
            query,
            signal_id,
            signal_type,
            tenant_id,
            investigation_id,
            json.dumps(input_context),
            json.dumps(output_response),
            automated_score,
            json.dumps(automated_dimensions) if automated_dimensions else None,
            model_version,
            source_event_id,
        )

        logger.debug(
            f"training_signal_recorded signal_id={signal_id} "
            f"signal_type={signal_type} investigation_id={investigation_id}"
        )

        return signal_id

    async def update_human_feedback(
        self,
        investigation_id: UUID,
        signal_type: str,
        score: float,
    ) -> None:
        """Update signal with human feedback score.

        Args:
            investigation_id: Investigation to update.
            signal_type: Type of signal to update.
            score: Human feedback score (-1, 0, or 1).
        """
        query = """
            UPDATE rl_training_signals
            SET human_feedback_score = $1
            WHERE investigation_id = $2 AND signal_type = $3
        """

        await self.db.execute(query, score, investigation_id, signal_type)

        logger.debug(
            f"human_feedback_updated investigation_id={investigation_id} "
            f"signal_type={signal_type} score={score}"
        )

    async def update_outcome_score(
        self,
        investigation_id: UUID,
        score: float,
    ) -> None:
        """Update signal with outcome score.

        Args:
            investigation_id: Investigation to update.
            score: Outcome score (0.0-1.0).
        """
        query = """
            UPDATE rl_training_signals
            SET outcome_score = $1
            WHERE investigation_id = $2
        """

        await self.db.execute(query, score, investigation_id)

        logger.debug(
            f"outcome_score_updated investigation_id={investigation_id} score={score}"
        )
```

**Step 5: Run test to verify it passes**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit/adapters/training/test_repository.py -v
```

Expected: PASS

**Step 6: Run lint and type check**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run ruff check src/dataing/adapters/training/ && uv run mypy src/dataing/adapters/training/
```

**Step 7: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/adapters/training/ backend/tests/unit/adapters/training/ && git commit -m "feat(training): add TrainingSignalRepository

Repository for persisting RL training signals:
- record_signal: capture input/output pairs with automated scores
- update_human_feedback: update with user feedback
- update_outcome_score: update with outcome tracking

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 4: Orchestrator Integration

### Task 4.1: Add Validator to OrchestratorConfig

**Files:**
- Modify: `backend/src/dataing/core/orchestrator.py:39-56`

**Step 1: Update OrchestratorConfig**

Edit `backend/src/dataing/core/orchestrator.py`, update the OrchestratorConfig dataclass:

```python
@dataclass(frozen=True)
class OrchestratorConfig:
    """Configuration for the investigation orchestrator.

    Attributes:
        max_hypotheses: Maximum number of hypotheses to generate.
        max_queries_per_hypothesis: Maximum queries per hypothesis.
        max_retries_per_hypothesis: Maximum retry attempts per hypothesis.
        query_timeout_seconds: Timeout for individual queries.
        high_confidence_threshold: Stop early if confidence exceeds this.
        validation_enabled: Whether to run quality validation.
        validation_pass_threshold: Minimum score to pass validation.
        validation_max_retries: Max retries when validation fails.
    """

    max_hypotheses: int = 5
    max_queries_per_hypothesis: int = 3
    max_retries_per_hypothesis: int = 2
    query_timeout_seconds: int = 30
    high_confidence_threshold: float = 0.85
    validation_enabled: bool = True
    validation_pass_threshold: float = 0.6
    validation_max_retries: int = 2
```

**Step 2: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/core/orchestrator.py && git commit -m "feat(orchestrator): add validation config options

Adds configuration for:
- validation_enabled: toggle validation on/off
- validation_pass_threshold: minimum score to pass
- validation_max_retries: max retries on validation failure

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4.2: Add Validator and Training Repo to Orchestrator

**Files:**
- Modify: `backend/src/dataing/core/orchestrator.py`

**Step 1: Update imports and constructor**

Edit `backend/src/dataing/core/orchestrator.py`, add to imports:

```python
if TYPE_CHECKING:
    from dataing.adapters.datasource.sql.base import SQLAdapter
    from dataing.adapters.training.repository import TrainingSignalRepository

    from ..safety.circuit_breaker import CircuitBreaker
    from .interfaces import ContextEngine, InvestigationFeedbackEmitter, LLMClient
    from .quality import QualityValidator
```

Update the `__init__` method:

```python
def __init__(
    self,
    db: SQLAdapter | None,
    llm: LLMClient,
    context_engine: ContextEngine,
    circuit_breaker: CircuitBreaker,
    config: OrchestratorConfig | None = None,
    feedback: InvestigationFeedbackEmitter | None = None,
    validator: QualityValidator | None = None,
    training_repo: TrainingSignalRepository | None = None,
) -> None:
    """Initialize the orchestrator.

    Args:
        db: Database adapter for executing queries (fallback). Can be None
            if adapters are always provided per-investigation.
        llm: LLM client for generating hypotheses and queries.
        context_engine: Engine for gathering investigation context.
        circuit_breaker: Safety circuit breaker.
        config: Optional orchestrator configuration.
        feedback: Optional feedback emitter for event logging.
        validator: Optional quality validator for LLM outputs.
        training_repo: Optional repository for training signal capture.
    """
    self.db = db
    self.llm = llm
    self.context_engine = context_engine
    self.circuit_breaker = circuit_breaker
    self.config = config or OrchestratorConfig()
    self.feedback = feedback
    self.validator = validator
    self.training_repo = training_repo
    # Will be set per-investigation when using tenant data source
    self._current_adapter: SQLAdapter | None = None
```

**Step 2: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/core/orchestrator.py && git commit -m "feat(orchestrator): add validator and training_repo dependencies

Injects QualityValidator and TrainingSignalRepository
for quality validation and training signal capture.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4.3: Implement Validation in Interpret Evidence

**Files:**
- Modify: `backend/src/dataing/core/orchestrator.py`

**Step 1: Add validation helper method**

Add this method to the InvestigationOrchestrator class:

```python
async def _validate_and_capture(
    self,
    state: InvestigationState,
    signal_type: str,
    input_context: dict[str, Any],
    output_response: Any,
    validation_fn: Any,
) -> tuple[Any, float | None]:
    """Validate output and capture training signal.

    Args:
        state: Current investigation state.
        signal_type: Type of output (interpretation, synthesis).
        input_context: Context provided to LLM.
        output_response: Response from LLM (Pydantic model).
        validation_fn: Async function to call for validation.

    Returns:
        Tuple of (possibly retried response, validation score or None).
    """
    if not self.config.validation_enabled or self.validator is None:
        return output_response, None

    validation_score: float | None = None

    for attempt in range(self.config.validation_max_retries + 1):
        result = await validation_fn(output_response)
        validation_score = result.assessment.composite_score

        if result.passed:
            break

        if attempt < self.config.validation_max_retries:
            logger.info(
                f"validation_retry signal_type={signal_type} "
                f"attempt={attempt + 1} "
                f"lowest_dimension={result.assessment.lowest_dimension}"
            )
            # Note: Retry logic would go here if we add quality_hint to LLM methods

    # Capture training signal
    if self.training_repo:
        await self.training_repo.record_signal(
            signal_type=signal_type,
            tenant_id=state.tenant_id,
            investigation_id=UUID(state.id),
            input_context=input_context,
            output_response=output_response.model_dump(),
            automated_score=validation_score,
            automated_dimensions=result.training_signals if result else None,
        )

    return output_response, validation_score
```

**Step 2: Update _investigate_hypothesis to validate interpretation**

Update the interpretation section in `_investigate_hypothesis`:

```python
# Interpret results
ev = await self.llm.interpret_evidence(hypothesis, query, result)

# Validate interpretation if enabled
if self.config.validation_enabled and self.validator:
    validation_result = await self.validator.validate_interpretation(
        response=ev._raw_response if hasattr(ev, '_raw_response') else None,
        hypothesis_title=hypothesis.title,
        query=query,
    )

    # Capture training signal
    if self.training_repo:
        await self.training_repo.record_signal(
            signal_type="interpretation",
            tenant_id=state.tenant_id,
            investigation_id=UUID(state.id),
            input_context={
                "hypothesis_title": hypothesis.title,
                "query": query,
                "row_count": result.row_count,
            },
            output_response={
                "interpretation": ev.interpretation,
                "confidence": ev.confidence,
                "supports_hypothesis": ev.supports_hypothesis,
            },
            automated_score=validation_result.assessment.composite_score,
            automated_dimensions=validation_result.training_signals,
        )

evidence.append(ev)
```

**Step 3: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/core/orchestrator.py && git commit -m "feat(orchestrator): add interpretation validation and signal capture

Validates interpretation outputs and captures training signals
for the RL pipeline.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4.4: Implement Validation in Synthesize

**Files:**
- Modify: `backend/src/dataing/core/orchestrator.py`

**Step 1: Update _synthesize method**

Update the `_synthesize` method to add validation:

```python
async def _synthesize(
    self,
    state: InvestigationState,
    evidence: list[Evidence],
    start_time: float,
) -> Finding:
    """Fan-in: Synthesize all evidence into a finding.

    Args:
        state: Current investigation state.
        evidence: All collected evidence.
        start_time: Investigation start time for duration calculation.

    Returns:
        Finding with root cause and recommendations.
    """
    finding = await self.llm.synthesize_findings(
        alert=state.alert,
        evidence=evidence,
    )

    # Validate synthesis if enabled
    validation_score: float | None = None
    if self.config.validation_enabled and self.validator:
        alert_summary = (
            f"{state.alert.metric_spec.display_name} on {state.alert.dataset_id}: "
            f"expected {state.alert.expected_value}, got {state.alert.actual_value} "
            f"({state.alert.deviation_pct}% deviation)"
        )

        # Get raw response for validation if available
        raw_response = getattr(finding, '_raw_response', None)
        if raw_response:
            validation_result = await self.validator.validate_synthesis(
                response=raw_response,
                alert_summary=alert_summary,
            )
            validation_score = validation_result.assessment.composite_score

            # Capture training signal
            if self.training_repo:
                await self.training_repo.record_signal(
                    signal_type="synthesis",
                    tenant_id=state.tenant_id,
                    investigation_id=UUID(state.id),
                    input_context={
                        "alert_summary": alert_summary,
                        "evidence_count": len(evidence),
                    },
                    output_response={
                        "root_cause": finding.root_cause,
                        "confidence": finding.confidence,
                        "recommendations": finding.recommendations,
                    },
                    automated_score=validation_score,
                    automated_dimensions=validation_result.training_signals,
                )

    # Update finding with investigation metadata
    duration = time.time() - start_time
    finding = Finding(
        investigation_id=state.id,
        status=finding.status,
        root_cause=finding.root_cause,
        confidence=finding.confidence,
        evidence=evidence,
        recommendations=finding.recommendations,
        duration_seconds=duration,
    )

    state.append_event(
        Event(
            type="synthesis_completed",
            timestamp=datetime.now(UTC),
            data={"root_cause": finding.root_cause, "confidence": finding.confidence},
        )
    )

    return finding
```

**Step 2: Add required import**

Add to imports at top of file:
```python
from typing import TYPE_CHECKING, Any
```

**Step 3: Run lint and type check**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run ruff check src/dataing/core/orchestrator.py && uv run mypy src/dataing/core/orchestrator.py
```

**Step 4: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/src/dataing/core/orchestrator.py && git commit -m "feat(orchestrator): add synthesis validation and signal capture

Validates synthesis outputs and captures training signals.
Completes the validation pipeline for interpretation + synthesis.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 5: Verification

### Task 5.1: Run Full Test Suite

**Step 1: Run all unit tests**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/unit -v --tb=short 2>&1 | tail -50
```

**Step 2: Run lint**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run ruff check src/dataing/
```

**Step 3: Run type check**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run mypy src/dataing/
```

**Step 4: Fix any issues found**

Address any lint, type, or test failures.

---

### Task 5.2: Create Integration Test

**Files:**
- Create: `backend/tests/integration/test_quality_validation.py`

**Step 1: Write integration test**

Create `backend/tests/integration/test_quality_validation.py`:
```python
"""Integration tests for quality validation pipeline."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from dataing.adapters.llm.response_models import InterpretationResponse, SynthesisResponse
from dataing.core.quality import LLMJudgeValidator, QualityAssessment


class TestQualityValidationIntegration:
    """Integration tests for the quality validation pipeline."""

    @pytest.fixture
    def mock_validator(self) -> LLMJudgeValidator:
        """Create a validator with mocked judge."""
        validator = LLMJudgeValidator.__new__(LLMJudgeValidator)
        validator.pass_threshold = 0.6
        validator.judge = MagicMock()
        validator.judge.run = AsyncMock()
        return validator

    @pytest.mark.asyncio
    async def test_shallow_interpretation_rejected(
        self, mock_validator: LLMJudgeValidator
    ) -> None:
        """Test that shallow interpretation is rejected."""
        # Configure mock to return low scores for shallow content
        mock_validator.judge.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.2,
                specificity=0.3,
                actionability=0.2,
                lowest_dimension="causal_depth",
                improvement_suggestion="Explain the causal chain from upstream cause to observed symptom",
            )
        )

        # Shallow interpretation that just confirms the symptom
        shallow_response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.9,
            interpretation="The query results confirm there are NULL values in the user_id column of the orders table.",
            causal_chain="NULL values exist in the data",
            key_findings=["NULLs found in user_id column"],
        )

        result = await mock_validator.validate_interpretation(
            response=shallow_response,
            hypothesis_title="NULL user_ids due to ETL failure",
            query="SELECT * FROM orders WHERE user_id IS NULL LIMIT 100",
        )

        assert result.passed is False
        assert result.assessment.causal_depth < 0.5

    @pytest.mark.asyncio
    async def test_good_interpretation_accepted(
        self, mock_validator: LLMJudgeValidator
    ) -> None:
        """Test that good interpretation is accepted."""
        mock_validator.judge.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.8,
                specificity=0.9,
                actionability=0.7,
                lowest_dimension="actionability",
                improvement_suggestion="Could add specific remediation commands",
            )
        )

        # Good interpretation with causal reasoning
        good_response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.85,
            interpretation=(
                "The 485 orphaned orders all appeared after 03:14 UTC. The users table shows "
                "no updates since 03:14 UTC, suggesting the upstream ETL job stopped. This "
                "temporal correlation indicates the users ETL failure caused the JOIN to produce NULLs."
            ),
            causal_chain="users ETL stopped at 03:14 UTC -> users table stale -> orders JOIN produces NULLs for new user_ids",
            key_findings=[
                "485 orders with NULL user_id",
                "All created after 03:14 UTC",
                "Last users table update: 03:14 UTC",
            ],
        )

        result = await mock_validator.validate_interpretation(
            response=good_response,
            hypothesis_title="NULL user_ids due to ETL failure",
            query="SELECT * FROM orders WHERE user_id IS NULL LIMIT 100",
        )

        assert result.passed is True
        assert result.assessment.causal_depth >= 0.7
```

**Step 2: Run integration test**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/integration/test_quality_validation.py -v
```

**Step 3: Commit**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git add backend/tests/integration/test_quality_validation.py && git commit -m "test: add quality validation integration tests

Tests that shallow interpretations are rejected and
good interpretations with causal reasoning are accepted.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 5.3: Final Verification and Summary

**Step 1: Run full test suite**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation/backend && uv run pytest tests/ -v --tb=short -q 2>&1 | tail -30
```

**Step 2: Verify all commits**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/quality-validation && git log --oneline feature/quality-validation ^main
```

**Step 3: Summary**

The implementation is complete when:
- [ ] All response models have structured causal reasoning fields
- [ ] QualityValidator protocol and LLMJudgeValidator are implemented
- [ ] rl_training_signals migration is created
- [ ] TrainingSignalRepository captures signals
- [ ] Orchestrator validates interpretation and synthesis
- [ ] All tests pass

---

## Files Created/Modified Summary

**New Files:**
- `backend/src/dataing/core/quality/__init__.py`
- `backend/src/dataing/core/quality/assessment.py`
- `backend/src/dataing/core/quality/protocol.py`
- `backend/src/dataing/core/quality/judge.py`
- `backend/src/dataing/adapters/training/__init__.py`
- `backend/src/dataing/adapters/training/types.py`
- `backend/src/dataing/adapters/training/repository.py`
- `backend/migrations/011_rl_training_signals.sql`
- `backend/tests/unit/adapters/llm/__init__.py`
- `backend/tests/unit/adapters/llm/test_response_models.py`
- `backend/tests/unit/core/quality/__init__.py`
- `backend/tests/unit/core/quality/test_assessment.py`
- `backend/tests/unit/core/quality/test_judge.py`
- `backend/tests/unit/adapters/training/__init__.py`
- `backend/tests/unit/adapters/training/test_repository.py`
- `backend/tests/integration/test_quality_validation.py`

**Modified Files:**
- `backend/src/dataing/adapters/llm/response_models.py`
- `backend/src/dataing/adapters/llm/client.py`
- `backend/src/dataing/core/orchestrator.py`
