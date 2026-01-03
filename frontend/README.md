# DataDr Frontend

Web application for DataDr - an AI-powered data quality investigation platform.

## Setup

```bash
# Install dependencies
pnpm install

# Start dev server
pnpm dev
```

The app runs at `http://localhost:5173`.

## Development Login

The app requires authentication. For local development, you can login using any API key:

1. Navigate to `http://localhost:5173`
2. You'll be redirected to the login page
3. Enter any text as the API key (e.g., `dev-key`)
4. Click "Sign in"

The authentication will accept any key when the backend validation endpoint isn't available, creating a demo tenant automatically.

## Scripts

- `pnpm dev` - Start development server
- `pnpm build` - Build for production
- `pnpm typecheck` - Run TypeScript checks
- `pnpm lint` - Run ESLint
