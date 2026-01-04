import { Avatar } from "@/components/ui/Avatar";
import { Tooltip } from "@/components/ui/Tooltip";
import { users } from "@/lib/api/mock-data";
import type { User } from "@/types/user";

export function PresenceIndicator({ viewers = users.slice(0, 3) }: { viewers?: User[] }) {
  return (
    <div className="flex -space-x-2">
      {viewers.map((viewer) => (
        <Tooltip key={viewer.id} content={`${viewer.name} is viewing`}>
          <Avatar src={viewer.avatar_url} name={viewer.name} size="sm" ring />
        </Tooltip>
      ))}
    </div>
  );
}
