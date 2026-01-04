"use client";

import { useState, Fragment } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { formatRelative } from "@/lib/utils/formatters";
import type { AuditEvent } from "@/types/admin";

export function AuditLogTable({ events }: { events: AuditEvent[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const getResourceDisplay = (event: AuditEvent) => {
    if (event.resource.id) {
      return `${event.resource.type}:${event.resource.id}`;
    }
    return event.resource.type;
  };

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-background-elevated/80">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border bg-background-elevated/60 text-xs uppercase tracking-widest text-foreground-muted">
          <tr>
            <th className="px-4 py-3">Actor</th>
            <th className="px-4 py-3">Action</th>
            <th className="px-4 py-3">Resource</th>
            <th className="px-4 py-3">When</th>
            <th className="w-12 px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <Fragment key={event.id}>
              <tr
                onClick={() => setExpandedId(expandedId === event.id ? null : event.id)}
                className="cursor-pointer border-b border-border hover:bg-background-subtle last:border-0"
              >
                <td className="px-4 py-3 font-medium text-foreground">{event.actor.email}</td>
                <td className="px-4 py-3 text-foreground-muted">{event.action}</td>
                <td className="px-4 py-3 text-foreground-muted">{getResourceDisplay(event)}</td>
                <td className="px-4 py-3 text-foreground-muted">{formatRelative(event.timestamp)}</td>
                <td className="px-4 py-3 text-foreground-muted">
                  {expandedId === event.id ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </td>
              </tr>
              {expandedId === event.id && (
                <tr className="bg-background-muted/50">
                  <td colSpan={5} className="p-4">
                    <div className="space-y-2">
                      <h4 className="text-xs font-semibold uppercase tracking-widest text-foreground-muted">
                        Event Details
                      </h4>
                      <div className="rounded-lg bg-background-elevated/60 p-3 font-mono text-xs">
                        <pre className="overflow-auto whitespace-pre-wrap text-foreground-muted">
                          {JSON.stringify(
                            {
                              id: event.id,
                              actor: event.actor,
                              action: event.action,
                              resource: event.resource,
                              timestamp: event.timestamp,
                              ip_address: event.ip_address,
                              metadata: event.metadata,
                            },
                            null,
                            2
                          )}
                        </pre>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
