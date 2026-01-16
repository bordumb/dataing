# fn-8.3 Create hero landing page (index.md)

## Description

Create a compelling hero landing page that positions dataing as "The AI Data Reliability Engineer."

### Create/Update File

`docs/docs/index.md` (replace existing content)

### Content Structure

1. **Hero Section:**
   - Headline: "The AI Data Reliability Engineer"
   - Subheadline: Detect anomalies → Generate hypotheses → Test with SQL → Find root causes
   - CTAs: "Get Started" → quickstart.md, "View on GitHub"

2. **How It Works:**
   - Mermaid diagram showing: Monitor → Detect → Investigate → Report flow
   - Brief explanation of agentic FSM architecture

3. **Key Features Grid (3 columns):**
   - **Auto Root Cause Analysis**: LLMs generate and test hypotheses in parallel
   - **Read-Only by Design**: Only SELECT queries, never modifies your data
   - **Human-in-the-Loop Gates**: Review and approve before any action

4. **Architecture Highlights:**
   - Hexagonal Architecture (Ports/Adapters)
   - Agentic Workflows (Maistro + Bond)
   - FSM Safety (Circuit breaker, query limits)

5. **Integrations:**
   - Data Warehouses: Snowflake, BigQuery, DuckDB, PostgreSQL
   - Lineage: OpenLineage, dbt, Dagster, Airflow

6. **Trust Signals:**
   - Link to security page
   - "Enterprise Ready" badge with SSO/RBAC mention

### References

- Existing homepage: `/docs/docs/index.md`
- Architecture: `/ARCHITECTURE.md`
## Acceptance
- [ ] Hero headline is "The AI Data Reliability Engineer"
- [ ] Mermaid diagram renders correctly
- [ ] Feature grid displays 3 items in columns
- [ ] CTA buttons link to quickstart.md and GitHub
- [ ] Integration logos/list present
- [ ] Link to security page exists
- [ ] No Lorem Ipsum or placeholder content
- [ ] Page renders correctly in both light and dark modes
## Done summary
- Created comprehensive hero landing page at docs/docs/index.md
- Added "The AI Data Reliability Engineer" headline with clear value proposition
- Included mermaid flowchart showing investigation workflow
- Added feature grid with Auto Root Cause, Read-Only, Human-in-the-Loop cards
- Added architecture highlights section explaining hexagonal architecture
- Included integration tables for data warehouses and lineage providers
- Added Enterprise Ready section with security, SSO/RBAC, self-hosted features
- Added Quick Start with pip/uv tabbed installation code blocks
- Build passes with `mkdocs build --strict`
## Evidence
- Commits: 4dda9aa550541aa4b622bb38a30d320e5b85c684
- Tests: mkdocs build --strict
- PRs:
