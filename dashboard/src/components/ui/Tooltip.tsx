export function Tooltip({
  content,
  children,
}: {
  content: string;
  children: React.ReactNode;
}) {
  return (
    <span className="relative inline-flex" title={content}>
      {children}
    </span>
  );
}
