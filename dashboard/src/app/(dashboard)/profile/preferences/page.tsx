"use client";

import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { usePreferencesStore } from "@/lib/stores/preferences-store";
import { useTheme } from "@/lib/theme";

export default function PreferencesPage() {
  const density = usePreferencesStore((state) => state.density);
  const notifications = usePreferencesStore((state) => state.notifications);
  const setDensity = usePreferencesStore((state) => state.setDensity);
  const setNotifications = usePreferencesStore((state) => state.setNotifications);
  const { theme, setTheme } = useTheme();

  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Preferences</h1>
      <Card title="Appearance">
        <div className="grid gap-4 md:grid-cols-2">
          <Select label="Theme" value={theme} onChange={(event) => setTheme(event.target.value as any)}>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
            <option value="system">System</option>
          </Select>
          <Select
            label="Density"
            value={density}
            onChange={(event) => setDensity(event.target.value as any)}
          >
            <option value="comfortable">Comfortable</option>
            <option value="compact">Compact</option>
          </Select>
        </div>
      </Card>

      <Card title="Notifications">
        <label className="flex items-center gap-3 text-sm font-medium text-foreground-muted">
          <input
            type="checkbox"
            checked={notifications}
            onChange={(event) => setNotifications(event.target.checked)}
          />
          Email me when investigations require approval.
        </label>
      </Card>
    </div>
  );
}
