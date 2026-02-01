# Contributing to Dataing

Thank you for your interest in contributing to Dataing. This guide will help you get started with development and understand our contribution process.

Please note that this project is released with a [Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Node.js 20 or higher
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [just](https://just.systems/) (command runner)
- [pnpm](https://pnpm.io/) (Node.js package manager)
- Docker (for running infrastructure locally)

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/bordumb/dataing.git
cd dataing

# Install all dependencies (Python + frontend)
just setup
```

### Verify Your Setup

```bash
# Start infrastructure (PostgreSQL, Redis, Jaeger)
just demo-infra

# Start the development servers (EE backend + frontend)
just dev
```

You should see:
- Backend: http://localhost:8000
- Frontend: http://localhost:3000

## Development Workflow

### Branching Model

- `main` is the protected default branch
- Create feature branches from `main` for your work
- Branch naming: `feat/<description>`, `fix/<description>`, `docs/<description>`

### Development Commands

```bash
# Run full dev stack (EE backend + frontend)
just dev

# Run backend only
just dev-backend      # EE backend
just dev-backend-ce   # CE backend only

# Run frontend only
just dev-frontend

# Run tests
just test             # All tests (CE + EE + frontend)
just test-ce          # CE tests only
just test-ee          # EE tests only
just test-frontend    # Frontend tests only

# Linting and formatting
just lint             # Run linters
just format           # Format code
just typecheck        # Run type checking

# Pre-commit checks
just pre-commit       # Run all pre-commit hooks
```

### Before Pushing

Always run these commands before pushing:

```bash
just lint
just format
just typecheck
just test
```

## Code Style

### Python

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

- Line length: 100 characters
- All public methods require docstrings (D102)
- All `__init__` methods require docstrings (D107)
- Use `isinstance(x, A | B)` instead of `isinstance(x, (A, B))`
- In except blocks, use `raise ... from e` or `raise ... from None`

### TypeScript/React

- Strict mode enabled
- ESLint and Prettier for linting/formatting
- Run `pnpm lint` and `pnpm format` in the frontend directory

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `chore`: Maintenance tasks
- `test`: Adding or updating tests
- `refactor`: Code refactoring (no feature change)

### Examples

```
feat(temporal): add retry logic for workflow activities
fix(api): handle null values in investigation response
docs: update quickstart guide
chore(deps): bump bond-agent to 0.5.0
test(core): add unit tests for state machine
refactor(adapters): simplify datasource factory pattern
```

## DCO Sign-Off

All commits must include a `Signed-off-by` line certifying that you have the right to submit the contribution under the project's license.

### What is the DCO?

The [Developer Certificate of Origin (DCO)](https://developercertificate.org) is a lightweight way for contributors to certify that they wrote or have the right to submit their contribution.

### How to Sign Off

Add the `-s` flag when committing:

```bash
git commit -s -m "feat: add new feature"
```

This adds a line like:
```
Signed-off-by: Your Name <your.email@example.com>
```

### Configure Git for Automatic Sign-Off

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

## Pull Request Process

1. **Create a branch** from `main`:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feat/my-feature
   ```

2. **Make your changes** and ensure tests pass:
   ```bash
   just lint
   just test
   ```

3. **Commit with sign-off**:
   ```bash
   git commit -s -m "feat: describe your change"
   ```

4. **Push and open a PR**:
   ```bash
   git push -u origin feat/my-feature
   ```

5. **Fill in the PR template** with:
   - Summary of changes
   - Test plan
   - Related issues

6. **Ensure CI is green** before requesting review

7. **Address review feedback** and update your PR

8. **Squash-merge** once approved (maintainers will handle this)

## Issue Triage

### Finding Issues to Work On

- Look for issues labeled `good first issue` for beginner-friendly tasks
- Check `help wanted` for issues where we need community help
- Comment on an issue to claim it before starting work

### Reporting Bugs

- Search existing issues first to avoid duplicates
- Use the bug report template
- Include reproduction steps, expected vs actual behavior

### Requesting Features

- Use the feature request template
- Explain the use case and proposed solution
- Be open to discussion and alternative approaches

## License

### Community Edition (CE)

The Community Edition in `python-packages/dataing/` is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

### Enterprise Edition (EE)

Code under `python-packages/dataing-ee/` has a separate enterprise license. External contributors should focus on CE contributions unless coordinating with maintainers.

## Community

- **Discord**: [Join our community](https://discord.gg/dataing) (coming soon)
- **GitHub Discussions**: Ask questions and share ideas
- **Issues**: Report bugs and request features

## Questions?

If you have questions about contributing, open a GitHub Discussion or reach out on Discord. We're happy to help you get started.

---

Thank you for contributing to Dataing!
