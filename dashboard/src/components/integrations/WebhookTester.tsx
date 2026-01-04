"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";

export function WebhookTester() {
  const [payload, setPayload] = useState("{\n  \"sample\": true\n}");
  const [status, setStatus] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      <Textarea
        rows={6}
        value={payload}
        onChange={(event) => setPayload(event.target.value)}
      />
      <div className="flex items-center justify-between">
        <Button onClick={() => setStatus("Payload sent to /api/webhooks")}>Send Test</Button>
        {status && <span className="text-xs text-foreground-muted">{status}</span>}
      </div>
    </div>
  );
}
