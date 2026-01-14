# fn-8.5 Create quickstart guide (quickstart.md)

## Description

Create a 5-minute quickstart guide that gets users to their first investigation.

### Create File

`docs/docs/quickstart.md`

### Content Structure

1. **Prerequisites:**
   - Python 3.11+
   - pip or uv
   - A data warehouse (DuckDB for demo, or BigQuery/Snowflake)

2. **Installation (Tabbed):**
   ```
   === "pip"
       pip install dataing-core

   === "uv"
       uv add dataing-core
   ```

3. **Configure Adapter (Tabbed):**
   - DuckDB tab (simplest for demo)
   - BigQuery tab (production)
   - Show environment variable setup

4. **Run First Investigation:**
   - CLI command: `dataing investigate --metric "null_rate" --table orders`
   - Or Python SDK example

5. **Sample Output:**
   - Show JSON output of successful investigation
   - Highlight root cause identification

6. **Next Steps:**
   - Link to configuration docs
   - Link to architecture overview
   - Link to security page

### References

- CLI commands: `/justfile:10-68`
- Demo fixtures: `/demo/fixtures/`
## Acceptance
- [ ] Prerequisites clearly listed
- [ ] Installation uses tabbed code blocks (pip vs uv)
- [ ] Adapter config uses tabbed code blocks (DuckDB vs BigQuery)
- [ ] CLI command example is copy-pasteable
- [ ] Sample JSON output shown
- [ ] Next steps section with links
- [ ] Takes approximately 5 minutes to follow
- [ ] No broken internal links
- [ ] Code blocks have copy buttons
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
