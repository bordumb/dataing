/**
 * Floating chat widget for the Dataing Assistant.
 *
 * Renders a floating button in the bottom-right corner that opens
 * a slide-out panel for chatting with the assistant.
 */

import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/Button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { AssistantPanel } from "./AssistantPanel";

export function AssistantWidget() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Floating button - bottom-right, above DemoToggle */}
      <Button
        className="fixed bottom-20 right-4 z-50 rounded-full shadow-lg h-12 w-12"
        size="icon"
        onClick={() => setOpen(true)}
        aria-label="Open assistant"
      >
        <MessageSquare className="h-5 w-5" />
      </Button>

      {/* Slide-out panel */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side="right"
          className="w-[400px] sm:w-[540px] p-0 flex flex-col"
        >
          <SheetHeader className="px-6 py-4 border-b">
            <SheetTitle>Dataing Assistant</SheetTitle>
            <SheetDescription>
              Ask about infrastructure, data issues, or investigations
            </SheetDescription>
          </SheetHeader>
          <div className="flex-1 overflow-hidden">
            <AssistantPanel />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
