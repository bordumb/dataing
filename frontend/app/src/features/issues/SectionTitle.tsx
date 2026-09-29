import { cn } from "@/lib/utils";

/** A heading in the issue sidebar's single panel (the mockup's `.side h3`). */
export function SectionTitle({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <h3
      className={cn(
        "mb-1.5 mt-3.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground",
        className,
      )}
    >
      {children}
    </h3>
  );
}
