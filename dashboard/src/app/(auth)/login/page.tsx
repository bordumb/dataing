import Link from "next/link";
import { Button } from "@/components/ui/Button";

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-grid px-6">
      <div className="w-full max-w-md rounded-2xl border border-border bg-background-elevated/80 p-8 shadow-soft">
        <h1 className="section-title text-3xl font-semibold">Welcome back</h1>
        <p className="mt-2 text-sm text-foreground-muted">Sign in with your SSO provider to access the dashboard.</p>
        <div className="mt-6 space-y-3">
          <Button className="w-full">Continue with SSO</Button>
          <Button variant="outline" className="w-full">Request access</Button>
        </div>
        <p className="mt-6 text-xs text-foreground-muted">
          By signing in you agree to the DataDr usage policy.
        </p>
        <Link href="/home" className="mt-4 inline-block text-xs font-semibold text-foreground">
          Continue to dashboard
        </Link>
      </div>
    </div>
  );
}
