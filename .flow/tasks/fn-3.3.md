# fn-3.3 GitHub API integration for PR lookup and author enrichment

## Description
Add GitHub API integration for PR lookup and author enrichment.

**Enhance GitHunterAdapter in `bond/src/bond/tools/githunter/_adapter.py` with:**

1. **`find_pr_discussion(repo_path, commit_hash)`** - Find PR associated with commit

2. **Author enrichment** - Lookup GitHub username from commit email in `blame_line()`

**Implementation details:**

1. **Parse remote URL** to get owner/repo:
   ```python
   # git -C <repo> remote get-url origin
   # Handle both SSH and HTTPS:
   # git@github.com:owner/repo.git -> owner/repo
   # https://github.com/owner/repo.git -> owner/repo
   ```

2. **GitHub API calls** (use httpx.AsyncClient):
   ```python
   headers = {
       'Accept': 'application/vnd.github+json',
       'Authorization': f'Bearer {token}',
       'X-GitHub-Api-Version': '2022-11-28'
   }
   ```

3. **Rate limiting**:
   - Check `X-RateLimit-Remaining` header after each call
   - On 403 with rate limit, raise `RateLimitedError(retry_after, reset_at)`

4. **Security**:
   - Read `GITHUB_TOKEN` from `os.environ.get('GITHUB_TOKEN')`
   - Never log token value or Authorization header
## Acceptance
- [ ] `find_pr_discussion(repo_path: Path, commit_hash: str)` returns `PRDiscussion | None`
- [ ] Returns None when commit has no associated PR (direct push to main)
- [ ] Fetches PR title, body, and issue comments (not review comments)
- [ ] Handles pagination for issue comments (per_page=100)
- [ ] Author enrichment adds github_username and github_avatar_url
- [ ] Uses httpx.AsyncClient with 30s timeout
- [ ] Includes proper Accept header: `application/vnd.github+json`
- [ ] Parses both SSH and HTTPS git remote URLs
- [ ] Raises `RateLimitedError` with retry_after_seconds on 403
- [ ] Logs warning when X-RateLimit-Remaining < 100
- [ ] GITHUB_TOKEN never appears in logs
- [ ] Graceful degradation: if no token, skip enrichment (don't fail)
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
