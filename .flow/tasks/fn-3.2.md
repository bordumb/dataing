# fn-3.2 blame_line implementation with git CLI

## Description
Implement `blame_line()` using async subprocess for git CLI.

**File to create:**
- `bond/src/bond/tools/githunter/_adapter.py` - GitHunterAdapter class

**Implementation details:**

1. **Async subprocess** - Use `asyncio.create_subprocess_exec` with 30s timeout:
   ```python
   proc = await asyncio.create_subprocess_exec(
       'git', '-C', str(repo_path), 'blame', '--porcelain', '-L', f'{line_no},{line_no}', '--', str(file_path),
       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
   )
   stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
   ```

2. **Parse porcelain output** - Extract: commit hash (first 40 chars), author, author-mail, author-time, summary

3. **Cache with HEAD SHA** - Before lookup, get `git rev-parse HEAD`. Cache key = `(repo_path, head_sha, file_path, line_no)`.

4. **Security** - Always `shell=False`, args as list, `--` before paths

**Edge cases:**
- File not in git repo → raise `RepoNotFoundError`
- Line number <= 0 or > file length → raise `LineOutOfRangeError`
- Shallow clone boundary (line starts with `^`) → set `is_boundary=True`
- Binary file → raise `BinaryFileError`
## Acceptance
- [ ] `blame_line(repo_path: Path, file_path: str, line_no: int)` returns `BlameResult`
- [ ] Uses `asyncio.create_subprocess_exec` with 30s timeout
- [ ] Parses `git blame --porcelain` output correctly
- [ ] Extracts: commit_hash, author, author-mail, author-time, summary
- [ ] Cache key includes HEAD SHA from `git rev-parse HEAD`
- [ ] Raises `RepoNotFoundError` for paths not in git repo
- [ ] Raises `LineOutOfRangeError` for invalid line numbers
- [ ] Raises `BinaryFileError` for binary files
- [ ] Sets `is_boundary=True` for shallow clone boundary commits
- [ ] Uses `shell=False` and `--` separator for security
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
