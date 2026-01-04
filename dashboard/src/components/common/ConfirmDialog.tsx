"use client";

import { Dialog, DialogContent, DialogTrigger, DialogClose } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";

export function ConfirmDialog({
  title,
  description,
  confirmLabel = "Confirm",
  onConfirm,
  trigger,
}: {
  title: string;
  description?: string;
  confirmLabel?: string;
  onConfirm: () => void;
  trigger: React.ReactNode;
}) {
  return (
    <Dialog>
      <DialogTrigger>{trigger}</DialogTrigger>
      <DialogContent>
        <h2 className="section-title text-lg font-semibold">{title}</h2>
        {description && <p className="mt-2 text-sm text-foreground-muted">{description}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <DialogClose>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
