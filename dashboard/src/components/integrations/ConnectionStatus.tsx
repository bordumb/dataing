export function ConnectionStatus({ status }: { status: "connected" | "warning" | "disconnected" }) {
  const statusStyles: Record<string, string> = {
    connected: "bg-success text-foreground-inverse",
    warning: "bg-warning text-foreground-inverse",
    disconnected: "bg-error text-foreground-inverse",
  };

  return <span className={`chip ${statusStyles[status]}`}>{status}</span>;
}
