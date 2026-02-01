# ADR: Branch Protection Settings

## Status

Accepted

## Context

The `main` branch is the primary integration branch for the project. To maintain code quality and prevent accidental breakage, we need to configure branch protection rules. These settings cannot be committed as files and must be applied via the GitHub UI or API.

## Decision

Apply the following branch protection rules to the `main` branch:

### Required Settings

1. **Require a pull request before merging**
   - Required approving reviews: 1
   - Dismiss stale pull request approvals when new commits are pushed
   - Require review from Code Owners

2. **Require status checks to pass before merging**
   - Require branches to be up to date before merging
   - Required status checks:
     - `CI / Backend Tests` (from ci-backend.yml)
     - `CI / Frontend Tests` (from ci-frontend.yml)
     - `Conventional Commits / Validate PR Title`
     - `DCO / DCO Sign-off Check`

3. **Require conversation resolution before merging**
   - Ensure all PR comments are resolved

4. **Do not allow bypassing the above settings**
   - Include administrators in restrictions

### Recommended Settings

5. **Require signed commits** (optional but recommended)
   - Enforces GPG-signed commits for cryptographic verification

6. **Do not allow force pushes**
   - Prevents rewriting history on main

7. **Do not allow deletions**
   - Prevents accidental branch deletion

## How to Apply

### Via GitHub UI

1. Go to repository Settings > Branches
2. Click "Add branch protection rule"
3. Set "Branch name pattern" to `main`
4. Check the boxes for each setting above
5. Click "Create" or "Save changes"

### Via GitHub CLI

```bash
gh api repos/{owner}/{repo}/branches/main/protection \
  -X PUT \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks='{"strict":true,"contexts":["CI / Backend Tests","CI / Frontend Tests","Conventional Commits / Validate PR Title","DCO / DCO Sign-off Check"]}' \
  -f enforce_admins=true \
  -f required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true,"require_code_owner_reviews":true}' \
  -f restrictions=null \
  -f required_linear_history=false \
  -f allow_force_pushes=false \
  -f allow_deletions=false
```

## Consequences

- All changes to `main` must go through pull requests
- PRs require at least one approval before merging
- CI must pass before merging
- Commit messages must follow conventional commits format
- All commits must be DCO signed-off
- Force pushes to `main` are prevented
- Code owners are automatically requested for review

## References

- [GitHub Branch Protection Documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Developer Certificate of Origin](https://developercertificate.org/)
