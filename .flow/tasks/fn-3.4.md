# fn-3.4 get_expert_for_file implementation

## Description
Implement `get_expert_for_file()` to determine code ownership based on commit frequency.

**Algorithm (deterministic):**

1. Run git log with commit window:
   ```bash
   git -C <repo> log --format='%aE|%aN|%H|%at' --follow --no-merges --since='90 days ago' -- <file>
   ```

2. Parse output, group by author email (case-insensitive)

3. Count commits per author

4. Sort by commit count descending

5. Return top N (default 3)

**Parameters:**
- `repo_path: Path` - Git repository path
- `file_path: str` - File path relative to repo
- `window_days: int = 90` - Time window for commit history
- `limit: int = 3` - Max experts to return

**Notes:**
- Use `--follow` to track file renames
- Use `--no-merges` to exclude merge commits
- If `window_days=0` or `None`, use all history (no --since)
## Acceptance
- [ ] `get_expert_for_file(repo_path, file_path, window_days=90, limit=3)` returns `list[FileExpert]`
- [ ] Uses git log with `--follow` to track renames
- [ ] Uses `--no-merges` to exclude merge commits
- [ ] Applies `--since` based on window_days parameter
- [ ] Groups commits by author email (case-insensitive)
- [ ] Returns experts sorted by commit_count descending
- [ ] Respects limit parameter (default 3)
- [ ] Includes last_commit_date for each expert
- [ ] Returns empty list for file with no commits (untracked/new)
- [ ] Uses async subprocess like blame_line
## Done summary
## Summary

Implemented get_expert_for_file() in GitHunterAdapter

### Implementation
- Uses `git log --format='%aE|%aN|%H|%at' --follow --no-merges`
- Groups commits by author email (case-insensitive)
- Sorts by commit count descending, returns top N
- Supports window_days parameter (0 = all history)
- Returns empty list for untracked/non-existent files

### Verification
- Smoke test: Found 1 expert (bordumb) with 10 commits for pyproject.toml
- Non-existent file returns empty list
- mypy --strict: passed
- ruff check: passed
## Evidence
- Commits: e9efa015
- Tests: mypy_passed, ruff_passed, smoke_test_passed
- PRs:
