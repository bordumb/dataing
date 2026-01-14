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
- Created comprehensive concepts section with 3 documentation pages
- investigations.md: Investigation loop, context gathering, hypothesis testing, synthesis
  - 4 mermaid diagrams (flow, query safety, parallel branches, lifecycle)
- agent-workflows.md: Maestro FSM, Steps, Signals, branching/merging
  - 2 mermaid diagrams (bounded vs unbounded, execution sequence)
- guardrails.md: SQL validator, circuit breaker, PII redactor
  - 2 mermaid diagrams (safety layer flow, PII flow)
- All content sourced from actual codebase (step.py, signals.py, validator.py, pii.py, circuit_breaker.py)
- Human-in-the-loop gates documented with AWAIT_USER signal
- Build passes with `mkdocs build --strict`
## Evidence
- Commits: d26eeeb473e756dfdb6f1f0b1e2085856f0df863
- Tests: mkdocs build --strict
- PRs:
