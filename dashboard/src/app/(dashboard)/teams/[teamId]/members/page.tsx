import { Card } from "@/components/ui/Card";
import { MemberList } from "@/components/teams/MemberList";
import { getTeamMembers } from "@/lib/api/teams";

export default async function TeamMembersPage({ params }: { params: { teamId: string } }) {
  const members = await getTeamMembers(params.teamId);
  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Team Members</h1>
      <Card>
        <MemberList members={members} />
      </Card>
    </div>
  );
}
