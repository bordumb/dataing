"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";

interface ScheduledReport {
  id: string;
  type: string;
  frequency: string;
}

export function ScheduledReports() {
  const [reports, setReports] = useState<ScheduledReport[]>([
    { id: "rep-001", type: "executive_summary", frequency: "weekly" },
  ]);

  const [frequency, setFrequency] = useState("weekly");
  const [reportType, setReportType] = useState("executive_summary");

  const addReport = () => {
    setReports((prev) => [
      { id: `rep-${prev.length + 2}`, type: reportType, frequency },
      ...prev,
    ]);
  };

  return (
    <Card title="Scheduled Reports" description="Automate periodic executive summaries.">
      <div className="grid gap-4 md:grid-cols-2">
        <Select label="Frequency" value={frequency} onChange={(event) => setFrequency(event.target.value)}>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </Select>
        <Select label="Report Type" value={reportType} onChange={(event) => setReportType(event.target.value)}>
          <option value="executive_summary">Executive Summary</option>
          <option value="mttr_trend">MTTR Trend</option>
          <option value="cost_breakdown">Cost Breakdown</option>
        </Select>
      </div>
      <div className="mt-4 flex justify-end">
        <Button onClick={addReport}>Schedule</Button>
      </div>
      <div className="mt-6 space-y-3">
        {reports.map((report) => (
          <div key={report.id} className="rounded-lg border border-border bg-background-elevated/70 p-3 text-sm">
            <p className="font-semibold text-foreground">{report.type}</p>
            <p className="text-xs text-foreground-muted">{report.frequency}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}
