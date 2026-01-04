import { Avatar } from "@/components/ui/Avatar";
import type { TeamMember } from "@/types/team";

export function MemberList({ members }: { members: TeamMember[] }) {
  return (
    <div className="space-y-3">
      {members.map((member) => (
        <div key={member.id} className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Avatar name={member.name} size="sm" />
            <div>
              <p className="text-sm font-semibold text-foreground">{member.name}</p>
              <p className="text-xs text-foreground-muted">{member.email}</p>
            </div>
          </div>
          <span className="text-xs font-semibold text-foreground-muted">{member.role}</span>
        </div>
      ))}
    </div>
  );
}
