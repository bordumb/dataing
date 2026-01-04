import { Card } from "@/components/ui/Card";
import { ConnectionStatus } from "@/components/integrations/ConnectionStatus";

export function IntegrationCard({
  title,
  description,
  status,
  action,
}: {
  title: string;
  description: string;
  status: "connected" | "warning" | "disconnected";
  action?: React.ReactNode;
}) {
  return (
    <Card title={title} description={description} actions={action}>
      <ConnectionStatus status={status} />
    </Card>
  );
}
