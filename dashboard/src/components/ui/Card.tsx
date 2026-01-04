import clsx from "clsx";

interface CardProps {
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function Card({ title, description, actions, children, className }: CardProps) {
  return (
    <section className={clsx("rounded-xl border border-border bg-background-elevated/80 p-5 shadow-card", className)}>
      {(title || actions) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="section-title text-lg font-semibold">{title}</h2>}
            {description && <p className="text-sm text-foreground-muted">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
