import { AuditLogTable } from "@/components/admin/AuditLogTable";
import { getAuditLog } from "@/lib/api/admin";

export const dynamic = 'force-dynamic';
export const revalidate = 60;

export default async function AuditLogPage() {
  const events = await getAuditLog();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Audit Log</h1>
        <p className="text-sm text-foreground-muted">Every administrative change across the org.</p>
      </div>
      <AuditLogTable events={events} />
    </div>
  );
}
