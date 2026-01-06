# Pydantic AI Structured Outputs Migration

## Overview

Replace fragile regex/JSON parsing in `AnthropicClient` with Pydantic AI's `response_model` for type-safe, self-validating LLM outputs.

## What Gets Removed

### Files to DELETE completely

| File | Lines | Reason |
|------|-------|--------|
| `backend/src/dataing/adapters/llm/prompt_manager.py` | 115 | Replaced by inline prompts |
| `backend/src/dataing/prompts/hypothesis.yaml` | 53 | JSON schema auto-generated |
| `backend/src/dataing/prompts/interpretation.yaml` | 31 | JSON schema auto-generated |
| `backend/src/dataing/prompts/synthesis.yaml` | 42 | JSON schema auto-generated |
| `backend/src/dataing/prompts/query.yaml` | 21 | Query prompts inline |
| `backend/src/dataing/prompts/reflexion.yaml` | 28 | Reflexion prompts inline |
| **Total** | **290** | Plus `prompts/` directory |

### Code to DELETE from `client.py`

- `_parse_hypotheses()` - 49 lines of regex JSON extraction
- `_extract_sql()` - 21 lines of SQL extraction
- `_parse_interpretation()` - 29 lines of JSON parsing with silent fallback
- `_parse_synthesis()` - 29 lines of JSON parsing with silent fallback
- All `re`, `json`, `uuid` imports used for parsing

**Net result:** ~420 lines removed, replaced by ~250 lines of typed response models + cleaner client.

## New Architecture

### File Structure

```
backend/src/dataing/adapters/llm/
├── __init__.py          # Updated exports
├── client.py            # Refactored: Pydantic AI agents, inline prompts
└── response_models.py   # NEW: Validated response schemas
```

### Flow

```
┌─────────────────────────────────────────────────────────────┐
│  AnthropicClient                                            │
│                                                             │
│  4 pre-configured Pydantic AI agents:                       │
│  - _hypothesis_agent (result_type=HypothesesResponse)       │
│  - _query_agent (result_type=QueryResponse)                 │
│  - _interpretation_agent (result_type=InterpretationResponse)│
│  - _synthesis_agent (result_type=SynthesisResponse)         │
│                                                             │
│  Pydantic AI handles:                                       │
│  1. Injects JSON schema into prompt automatically           │
│  2. Calls Claude API                                        │
│  3. Validates response against Pydantic model               │
│  4. Auto-retries on validation failure (up to 3x)           │
└─────────────────────────────────────────────────────────────┘
```

### Response Models

Response models enforce quality at the LLM boundary:

- `HypothesisResponse` - validates query has LIMIT, no mutations
- `HypothesesResponse` - 1-10 hypotheses required
- `QueryResponse` - strips markdown, validates SELECT-only with LIMIT
- `InterpretationResponse` - confidence 0.0-1.0, interpretation min 20 chars
- `SynthesisResponse` - root cause min 20 chars (or null), 1-5 recommendations

## Implementation Steps

### Phase 1: Setup
1. Add `pydantic-ai>=0.0.14` to `pyproject.toml`
2. Create `response_models.py` with validated schemas

### Phase 2: Refactor
3. Rewrite `client.py` with Pydantic AI agents and inline prompts

### Phase 3: Cleanup
4. Delete `prompt_manager.py`
5. Delete `backend/src/dataing/prompts/` directory
6. Update `__init__.py` exports

### Phase 4: Tests
7. Create `test_response_models.py` with validator tests

### Phase 5: Verify
8. Run `just lint` and `just test`
