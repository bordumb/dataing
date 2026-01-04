import clsx from "clsx";
import { statusClasses } from "@/lib/utils/colors";
import type { InvestigationStatus } from "@/types/investigation";

export function StatusBadge({ status }: { status: InvestigationStatus }) {
  return (
    <span className={clsx("chip", statusClasses[status])}>
      {status.replace("_", " ")}
    </span>
  );
}
