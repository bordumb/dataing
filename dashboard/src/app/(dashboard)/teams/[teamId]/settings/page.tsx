import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { getTeam } from "@/lib/api/teams";

export default async function TeamSettingsPage({ params }: { params: { teamId: string } }) {
  const team = await getTeam(params.teamId);
  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">{team.name} Settings</h1>
      <Card title="Team Profile">
        <div className="grid gap-4 md:grid-cols-2">
          <Input defaultValue={team.name} />
          <Select label="Default escalation" defaultValue="slack">
            <option value="slack">Slack</option>
            <option value="pagerduty">PagerDuty</option>
          </Select>
        </div>
        <div className="mt-4 flex justify-end">
          <Button>Update</Button>
        </div>
      </Card>
    </div>
  );
}
