export default function CallbackPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-grid px-6">
      <div className="rounded-2xl border border-border bg-background-elevated/80 p-8 shadow-soft">
        <h1 className="section-title text-2xl font-semibold">Signing you in...</h1>
        <p className="mt-2 text-sm text-foreground-muted">Hang tight while we finalize authentication.</p>
      </div>
    </div>
  );
}
