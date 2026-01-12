# fn-3.1 Types and Protocol definitions

## Description
Create the foundational types and protocol for Git Hunter as an agent tool.

**Files to create:**
- `bond/src/bond/tools/githunter/__init__.py`
- `bond/src/bond/tools/githunter/_types.py`
- `bond/src/bond/tools/githunter/_protocols.py`
- `bond/src/bond/tools/githunter/_exceptions.py`

**Types to define (frozen dataclasses):**

```python
@dataclass(frozen=True)
class AuthorProfile:
    git_email: str
    git_name: str
    github_username: str | None = None
    github_avatar_url: str | None = None

@dataclass(frozen=True)
class BlameResult:
    line_no: int
    content: str
    author: AuthorProfile
    commit_hash: str
    commit_date: datetime  # UTC, author date
    commit_message: str
    is_boundary: bool = False  # True if shallow clone boundary

@dataclass(frozen=True)
class FileExpert:
    author: AuthorProfile
    commit_count: int
    last_commit_date: datetime  # UTC

@dataclass(frozen=True)
class PRDiscussion:
    pr_number: int
    title: str
    body: str
    url: str
    issue_comments: list[str]  # Top-level PR comments only
```

**Protocol to define:**
- `GitHunterProtocol(Protocol)` with `@runtime_checkable`
- All methods take `repo_path: Path` as first argument
- Methods: `blame_line()`, `find_pr_discussion()`, `get_expert_for_file()`
## Acceptance
- [ ] `AuthorProfile` dataclass with git_email, git_name, github_username, github_avatar_url
- [ ] `BlameResult` dataclass with nested AuthorProfile, commit_hash, commit_date (UTC datetime)
- [ ] `FileExpert` dataclass with commit_count and last_commit_date
- [ ] `PRDiscussion` dataclass with issue_comments (not review comments)
- [ ] `GitHunterProtocol` with runtime_checkable decorator
- [ ] All protocol methods take `repo_path: Path` as first argument
- [ ] Exception hierarchy: GitHunterError, RepoNotFoundError, FileNotFoundError, LineOutOfRangeError, BinaryFileError, ShallowCloneError, RateLimitedError, GitHubUnavailableError
- [ ] RateLimitedError stores retry_after_seconds and reset_at
- [ ] mypy passes with strict mode
- [ ] ruff passes (D102, D107 docstrings)
## Done summary
## Summary

Created types and protocol definitions for Git Hunter in bond/src/bond/tools/githunter/

### Files Created
- `_types.py` - AuthorProfile, BlameResult, FileExpert, PRDiscussion frozen dataclasses
- `_protocols.py` - GitHunterProtocol with runtime_checkable decorator
- `_exceptions.py` - Exception hierarchy with RateLimitedError storing retry details
- `__init__.py` - Public exports

### Verification
- mypy --strict: passed (4 source files)
- ruff check: passed
## Evidence
- Commits: 904ff4ce
- Tests: mypy_passed, ruff_passed
- PRs:
