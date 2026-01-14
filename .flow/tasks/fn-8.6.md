# fn-8.6 Create architecture overview page

## Description

Create a high-level architecture overview page with a Mermaid diagram showing Core vs Adapters.

### Create File

`docs/docs/architecture.md`

### Content Structure

1. **High-Level Diagram (Mermaid):**
   ```mermaid
   flowchart TB
       subgraph Adapters["Adapters (Ports)"]
           DW[Data Warehouses]
           LN[Lineage Providers]
           NT[Notifications]
       end
       subgraph Core["Core Domain"]
           INV[Investigation Engine]
           AGT[Agent Runtime<br/>Bond + Maestro]
           SFT[Safety Layer]
       end
       DW --> INV
       LN --> INV
       INV --> AGT
       AGT --> SFT
       SFT --> NT
   ```

2. **Hexagonal Architecture:**
   - Core domain is framework-agnostic
   - Adapters implement ports (interfaces)
   - Easy to swap implementations

3. **Key Components:**
   - **Investigation Engine**: Orchestrates the investigation workflow
   - **Bond**: Agent runtime (PydanticAI wrapper)
   - **Maestro**: Workflow FSM (Steps, Signals, Branching)
   - **Safety Layer**: Query validation, rate limiting, PII masking

4. **Data Flow:**
   - Monitor → Detect anomaly → Trigger investigation
   - Gather context → Generate hypotheses → Test with SQL
   - Synthesize findings → Report

### Source Code References

- `/dataing/src/dataing/core/` - Core domain
- `/dataing/src/dataing/adapters/` - Adapter implementations
- `/maestro/src/maestro/` - Workflow engine
- `/bond/src/bond/` - Agent runtime
## Acceptance
- [ ] File exists at `docs/docs/architecture.md`
- [ ] Mermaid diagram renders correctly
- [ ] Hexagonal architecture explained
- [ ] Bond and Maestro mentioned
- [ ] Safety layer described
- [ ] Data flow visualized or described
- [ ] Links to deeper concept pages
## Done summary
- Created comprehensive architecture overview at docs/docs/architecture.md
- Added high-level mermaid flowchart showing Core, Adapters, External Services
- Explained hexagonal architecture with ports and adapters pattern
- Documented package dependency order (maestro → bond → dataing)
- Described Maestro workflow engine: Steps protocol, Signals, Branching
- Described Bond agent runtime with BondStep template pattern
- Added safety layer overview (validator, PII, circuit breaker)
- Included sequence diagram showing investigation data flow
- Added "Learn More" card grid linking to concept pages
- Build passes with `mkdocs build --strict`
## Evidence
- Commits: 1511058136a8603174ed5f777bb36bd4f2651c46
- Tests: mkdocs build --strict
- PRs:
