# fn-8.7 Create concepts section (investigations, agent-workflows, guardrails)

## Description

Create the concepts section explaining how investigations work, the Maestro FSM, and safety guardrails.

### Create Files

- `docs/docs/concepts/investigations.md`
- `docs/docs/concepts/agent-workflows.md`
- `docs/docs/concepts/guardrails.md`

### investigations.md Content

1. **The Investigation Loop:**
   - Gather → Hypothesize → Verify → Synthesize
   - Diagram showing the flow

2. **Hypothesis Generation:**
   - How LLMs generate multiple hypotheses
   - Context-aware reasoning
   - Reference: `generate_hypotheses.py`

3. **Evidence Gathering:**
   - Stats collection before querying
   - Metadata analysis
   - Reference: `gather_context.py`

4. **Synthesis:**
   - Root cause identification
   - Confidence scoring
   - Reference: `synthesize.py`

### agent-workflows.md Content

1. **The State Machine (Maestro):**
   - Explain FSM prevents open-loop hallucination
   - Steps define deterministic actions
   - Signals control flow (CONTINUE, COMPLETE, SUSPEND)

2. **Human-in-the-Loop:**
   - `Signal.SUSPEND` for approval gates
   - Users can approve/reject before actions

3. **Step Protocol:**
   - `execute()` method contract
   - Input/Output typing
   - Reference: `/maestro/src/maestro/step.py`

### guardrails.md Content

1. **Query Validation:**
   - SELECT-only enforcement
   - FORBIDDEN_STATEMENTS list
   - sqlglot parsing
   - Reference: `validator.py`

2. **Circuit Breaker:**
   - Max 50 queries per investigation
   - 10-minute timeout
   - Reference: `circuit_breaker.py`

3. **PII Masking:**
   - Detected patterns (email, SSN, CC, phone, ZIP)
   - Auto-redaction before LLM
   - Reference: `pii.py`

### Source Code References

- `/dataing/src/dataing/core/investigation/steps/`
- `/maestro/src/maestro/`
- `/dataing/src/dataing/safety/`
## Acceptance
- [ ] `concepts/investigations.md` explains the loop
- [ ] `concepts/agent-workflows.md` explains Maestro FSM
- [ ] `concepts/guardrails.md` documents safety features
- [ ] Mermaid diagrams where appropriate
- [ ] Code references accurate (validator.py, circuit_breaker.py)
- [ ] Human-in-the-loop explained
- [ ] PII detection types listed
- [ ] All pages render correctly
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
