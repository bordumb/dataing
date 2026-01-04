# Dashboard

Next.js 14 dashboard for DataDr - view and manage data quality investigations.

# Quick Start

```bash
# Install dependencies
pnpm install

# Start development server
pnpm dev
```

The dashboard runs at http://localhost:3000

# Development

### Build

```bash
# Production build
pnpm build

# Type checking
pnpm typecheck

# Linting
pnpm lint
```

## Testing

### E2E Tests (Playwright)

#### Real API Calls
```bash
# Run all E2E tests (requires demo services running)
pnpm test:e2e

# Run with demo services auto-start
pnpm test:e2e:full

# Run with UI mode
pnpm test:e2e:ui

# Run specific test file
pnpm exec playwright test e2e/home.spec.ts

# Run headed (visible browser)
pnpm test:e2e:headed

# Show HTML report after tests
pnpm test:e2e:report
```

The `test:e2e:full` script will:
1. Start the demo Docker containers if not running
2. Wait for the API to be healthy
3. Run all Playwright tests

#### API Mocking (HAR Recording/Replay)

E2E tests support API mocking using Playwright's HAR (HTTP Archive) recording/replay. This approach is scalable - when the API changes, just re-record the HAR file.

```bash
pnpm test:e2e:record
```
> Note: This only needs to be run each time there is a change to the API logic. This will run the actual API calls, and record the responses for future use.

Run tests with mocked API (no API needed):
```
pnpm test:e2e:mock
```

**How it works:**
1. `test:e2e:record` runs tests against a live API and saves all responses to `e2e/fixtures/api-responses.har`
2. `test:e2e:mock` replays responses from the HAR file, making tests fast and independent of the API

**Custom mocking for edge cases:**
```typescript
import { test, mockApiError, mockEmptyResponse } from "./fixtures";

test("handles API error gracefully", async ({ page }) => {
  await mockApiError(page, /\/api\/investigations/, 500, "Server error");
  // Test error handling...
});

test("shows empty state", async ({ page }) => {
  await mockEmptyResponse(page, /\/api\/datasets/);
  // Test empty state...
});
```

#### CI Test Suite

```bash
# Lint + typecheck + build
pnpm test:ci

# Full clean install + test
pnpm test:ci:full
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | API URL for browser requests | `http://localhost:8000` |
| `API_INTERNAL_URL` | API URL for server-side requests | `http://api:8000` |
| `NEXTAUTH_URL` | NextAuth base URL | `http://localhost:3000` |
| `NEXTAUTH_SECRET` | NextAuth secret key | - |

## Project Structure

```
dashboard/
├── src/
│   ├── app/           # Next.js App Router pages
│   ├── components/    # React components
│   └── lib/api/       # API client functions
├── e2e/               # Playwright E2E tests
└── public/            # Static assets
```
