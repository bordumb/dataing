export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border-strong bg-background-elevated/40 p-8 text-center">
      <h3 className="section-title text-lg font-semibold">{title}</h3>
      {description && <p className="mt-2 text-sm text-foreground-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
