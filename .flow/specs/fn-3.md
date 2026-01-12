# Git Hunter: Forensic Code Ownership Tool

## Overview

Git Hunter bridges the gap between code/data and people. It allows the investigation agent to traverse version control history, map commits to authors, and determine "who knows what" about specific code files.

**Primary Use Cases:**
1. Find who last modified a specific line (e.g., schema migration that made column nullable)
2. Fetch PR discussion context for a commit to understand the "why"
3. Determine the expert/owner of a file based on commit frequency

## Scope

### In Scope
- `blame_line(repo_path, file_path, line_no)` → BlameResult with AuthorProfile
- `find_pr_discussion(repo_path, commit_hash)` → PRDiscussion | None
- `get_expert_for_file(repo_path, file_path, window_days)` → list[FileExpert]
- Local git CLI integration via `asyncio.create_subprocess_exec`
- GitHub REST API for PR lookup and author enrichment
- LRU cache with repo HEAD SHA in cache key

### Out of Scope (v1)
- GitLab/Bitbucket support (GitHub only)
- Org chart integration (future enhancement)
- Real-time webhook-based cache invalidation
- Support for git submodules

## Approach

This is an **agent tool** (not a data adapter), so it lives in `bond/tools/`:

```
bond/src/bond/tools/githunter/
├── __init__.py
├── _types.py         # AuthorProfile, BlameResult, FileExpert, PRDiscussion
├── _protocols.py     # GitHunterProtocol (runtime_checkable)
├── _exceptions.py    # GitHunterError, RepoNotFoundError, RateLimitedError
└── _adapter.py       # GitHunterAdapter implementation
```

**Key Design Decisions:**

1. **Async subprocess** - Use `asyncio.create_subprocess_exec` with timeout for all git commands. Never use blocking `subprocess.run` in async context.

2. **Repo identification** - All methods take `repo_path: Path` as first arg. Adapter parses remote URL via `git -C <repo_path> remote get-url origin` to extract `owner/repo` for GitHub API.

3. **GitHub auth** - Token from `GITHUB_TOKEN` env var. Never log token or `Authorization` headers.

4. **Cache keying** - Include `(repo_path, repo_head_sha, file_path, line_no)` in cache key. Fetch HEAD SHA via `git rev-parse HEAD` before cache lookup.

5. **Security** - Always use `shell=False`, pass args as list, use `--` separator before paths, validate inputs.

**Git Commands Used:**

```bash
# Blame single line (porcelain format for parsing)
git -C <repo> blame --porcelain -L <n>,<n> -- <file>

# Get commit history for expert ranking
git -C <repo> log --format='%aE|%aN|%H|%at' --follow --no-merges --since='<N> days ago' -- <file>

# Get repo HEAD for cache key
git -C <repo> rev-parse HEAD

# Get remote URL for GitHub API
git -C <repo> remote get-url origin
```

**GitHub API Endpoints:**

```
# Find PRs containing commit (requires Accept: application/vnd.github+json)
GET /repos/{owner}/{repo}/commits/{sha}/pulls

# Get PR details
GET /repos/{owner}/{repo}/pulls/{number}

# Get PR issue comments (top-level discussion)
GET /repos/{owner}/{repo}/issues/{number}/comments?per_page=100

# Search user by email (for author enrichment)
GET /search/users?q={email}+in:email
```

## Quick Commands

```bash
# Run unit tests
cd bond && uv run pytest tests/unit/tools/githunter/ -v

# Type check
cd bond && uv run mypy src/bond/tools/githunter/

# Smoke test (requires GITHUB_TOKEN and git repo)
cd bond && uv run python -c "
import asyncio
from pathlib import Path
from bond.tools.githunter import GitHunterAdapter

async def test():
    adapter = GitHunterAdapter()
    result = await adapter.blame_line(Path('.'), 'pyproject.toml', 1)
    print(result)

asyncio.run(test())
"
```

## Acceptance Criteria

- [ ] All methods take `repo_path: Path` as first argument
- [ ] Uses `asyncio.create_subprocess_exec` (not blocking subprocess)
- [ ] `blame_line()` returns `BlameResult` containing `AuthorProfile`
- [ ] `blame_line()` parses `git blame --porcelain` output correctly
- [ ] `find_pr_discussion()` returns `PRDiscussion | None`
- [ ] `find_pr_discussion()` returns None when commit has no PR (direct push)
- [ ] `find_pr_discussion()` fetches PR title, body, and issue comments
- [ ] `get_expert_for_file()` returns ranked `list[FileExpert]` by commit count
- [ ] `get_expert_for_file()` accepts `window_days` parameter (default 90)
- [ ] GitHub API calls include proper Accept header and handle pagination
- [ ] Rate limiting raises `RateLimitedError(retry_after_seconds, reset_at)`
- [ ] Cache keys include repo HEAD SHA to invalidate on new commits
- [ ] All subprocess calls use `shell=False` with `--` path separator
- [ ] GITHUB_TOKEN never logged; Authorization headers redacted in debug logs
- [ ] Unit tests with mocked git/GitHub responses
- [ ] Docstrings on all public methods (ruff D102/D107 compliance)

## Error Handling

| Error | When | Behavior |
|-------|------|----------|
| `RepoNotFoundError` | Path not in git repo | Raise immediately |
| `FileNotFoundError` | File doesn't exist in repo | Raise immediately |
| `LineOutOfRangeError` | Line number invalid | Raise immediately |
| `BinaryFileError` | Blame on binary file | Raise immediately |
| `ShallowCloneError` | Shallow clone detected | Return partial with `is_incomplete_history=True` |
| `RateLimitedError` | GitHub 403 rate limit | Raise with `retry_after_seconds` |
| `GitHubUnavailableError` | GitHub API down | Return partial data (blame works, no enrichment) |

## References

**Codebase patterns to follow:**
- Bond tools structure: `bond/src/bond/tools/`
- Protocol pattern: `dataing/src/dataing/core/interfaces.py:29-75`

**External docs:**
- GitHub REST API: https://docs.github.com/en/rest
- git-blame porcelain: https://git-scm.com/docs/git-blame#_the_porcelain_format
