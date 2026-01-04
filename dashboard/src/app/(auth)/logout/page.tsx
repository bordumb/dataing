import Link from "next/link";
import { Button } from "@/components/ui/Button";

export default function LogoutPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-grid px-6">
      <div className="w-full max-w-md rounded-2xl border border-border bg-background-elevated/80 p-8 shadow-soft">
        <h1 className="section-title text-3xl font-semibold">You are signed out</h1>
        <p className="mt-2 text-sm text-foreground-muted">Thanks for keeping your workspace secure.</p>
        <div className="mt-6">
          <Link href="/login">
            <Button className="w-full">Sign in again</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
