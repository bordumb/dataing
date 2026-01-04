import Image from "next/image";
import clsx from "clsx";

const sizeClasses: Record<string, string> = {
  sm: "h-8 w-8",
  md: "h-10 w-10",
  lg: "h-14 w-14",
  xl: "h-20 w-20",
};

export function Avatar({
  src,
  name,
  size = "md",
  ring,
}: {
  src?: string;
  name?: string;
  size?: keyof typeof sizeClasses;
  ring?: boolean;
}) {
  const initials = name
    ? name
        .split(" ")
        .map((part) => part[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "";

  return (
    <div
      className={clsx(
        "relative overflow-hidden rounded-full bg-background-muted text-xs font-semibold text-foreground/70",
        sizeClasses[size],
        ring && "ring-2 ring-background",
      )}
    >
      {src ? (
        <Image
          src={src}
          alt={name ?? "avatar"}
          fill
          sizes="64px"
          className="object-cover"
          unoptimized
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">{initials}</div>
      )}
    </div>
  );
}
