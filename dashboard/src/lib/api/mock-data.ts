import type { Dataset, DatasetAnomaly, DatasetLineage } from "@/types/dataset";
import type { Investigation } from "@/types/investigation";
import type { OrgStats } from "@/types/analytics";
import type { Team, TeamMember } from "@/types/team";
import type { User, UserActivity } from "@/types/user";

const now = Date.now();
const iso = (offsetHours: number) => new Date(now - offsetHours * 3600 * 1000).toISOString();

export const org = {
  id: "org-001",
  name: "Northwind Holdings",
  user_count: 128,
  team_count: 8,
  plan: "Enterprise",
};

export const teams: Team[] = [
  {
    id: "team-001",
    name: "Revenue Ops",
    description: "Owns revenue critical pipelines and SLAs.",
    member_count: 18,
    dataset_count: 12,
    lead: "Avery Park",
  },
  {
    id: "team-002",
    name: "Customer Insights",
    description: "Behavioral analytics and lifecycle reporting.",
    member_count: 12,
    dataset_count: 9,
    lead: "Ravi Singh",
  },
  {
    id: "team-003",
    name: "Platform Reliability",
    description: "Monitors data platform performance and cost.",
    member_count: 9,
    dataset_count: 6,
    lead: "Lucia Torres",
  },
];

export const teamMembers: Record<string, TeamMember[]> = {
  "team-001": [
    {
      id: "user-001",
      name: "Avery Park",
      email: "avery.park@datadr.io",
      role: "Team Lead",
    },
    {
      id: "user-002",
      name: "Jordan Li",
      email: "jordan.li@datadr.io",
      role: "Analytics Engineer",
    },
  ],
  "team-002": [
    {
      id: "user-003",
      name: "Ravi Singh",
      email: "ravi.singh@datadr.io",
      role: "Team Lead",
    },
  ],
  "team-003": [
    {
      id: "user-004",
      name: "Lucia Torres",
      email: "lucia.torres@datadr.io",
      role: "SRE",
    },
  ],
};

export const users: User[] = [
  {
    id: "user-001",
    name: "Avery Park",
    email: "avery.park@datadr.io",
    role: "admin",
    roles: ["admin"],
    avatar_url: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=facearea&w=96&q=80",
    teams: [{ id: "team-001", name: "Revenue Ops" }],
    last_active_at: iso(2),
    stats: {
      investigations_triggered: 18,
      approvals_given: 42,
      knowledge_entries: 7,
    },
  },
  {
    id: "user-002",
    name: "Jordan Li",
    email: "jordan.li@datadr.io",
    role: "member",
    roles: ["member"],
    avatar_url: "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=facearea&w=96&q=80",
    teams: [
      { id: "team-001", name: "Revenue Ops" },
      { id: "team-003", name: "Platform Reliability" },
    ],
    last_active_at: iso(6),
    stats: {
      investigations_triggered: 6,
      approvals_given: 11,
      knowledge_entries: 2,
    },
  },
  {
    id: "user-003",
    name: "Ravi Singh",
    email: "ravi.singh@datadr.io",
    role: "viewer",
    roles: ["viewer"],
    avatar_url: "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=facearea&w=96&q=80",
    teams: [{ id: "team-002", name: "Customer Insights" }],
    last_active_at: iso(12),
    stats: {
      investigations_triggered: 2,
      approvals_given: 0,
      knowledge_entries: 1,
    },
  },
];

export const datasets: Dataset[] = [
  {
    id: "ds-001",
    name: "orders_fact",
    description: "Core order transactions across channels.",
    owner_team_id: "team-001",
    table_count: 12,
    investigation_count: 8,
    anomaly_count_30d: 4,
    freshness_status: "warning",
  },
  {
    id: "ds-002",
    name: "subscriptions_daily",
    description: "Daily subscription lifecycle metrics.",
    owner_team_id: "team-002",
    table_count: 7,
    investigation_count: 5,
    anomaly_count_30d: 2,
    freshness_status: "healthy",
  },
  {
    id: "ds-003",
    name: "warehouse_loads",
    description: "Pipeline health and SLA tracking.",
    owner_team_id: "team-003",
    table_count: 4,
    investigation_count: 3,
    anomaly_count_30d: 1,
    freshness_status: "critical",
  },
];

export const investigations: Investigation[] = [
  {
    id: "inv-001",
    title: "Orders revenue drop in APAC",
    status: "active",
    dataset_id: "ds-001",
    triggered_by: users[0],
    trigger_source: "Monte Carlo",
    started_at: iso(10),
    updated_at: iso(2),
    mttr_hours: 3.4,
    root_cause: "Delayed ingestion from payment processor",
    summary: "Revenue dip aligns with missing APAC payments feed.",
    transcript: [
      {
        id: "step-001",
        title: "Ingest anomaly alert",
        detail: "Volume dropped 18% from baseline.",
        status: "complete",
        created_at: iso(10),
      },
      {
        id: "step-002",
        title: "Validate upstream feeds",
        detail: "Payments API returning partial payloads.",
        status: "active",
        created_at: iso(6),
      },
      {
        id: "step-003",
        title: "Recommend remediation",
        detail: "Throttle retries and backfill once API recovers.",
        status: "pending",
        created_at: iso(2),
      },
    ],
    artifacts: [
      {
        id: "art-001",
        type: "sql",
        title: "Volume check query",
        content: "SELECT channel, COUNT(*) FROM orders_fact WHERE order_date >= CURRENT_DATE - INTERVAL '7' DAY GROUP BY 1;",
      },
      {
        id: "art-002",
        type: "note",
        title: "Investigation summary",
        content: "APAC payments feed delayed by 45 minutes; evaluate retry policy.",
      },
    ],
    diagnosis: {
      summary: "Delay in the APAC payments feed caused downstream volume drop.",
      confidence: 0.76,
      root_cause: "Upstream API throttling",
      recommendations: [
        "Increase backfill window",
        "Add alerts on retry saturation",
      ],
    },
  },
  {
    id: "inv-002",
    title: "Subscription churn spike",
    status: "awaiting_approval",
    dataset_id: "ds-002",
    triggered_by: users[2],
    trigger_source: "Anomalo",
    started_at: iso(18),
    updated_at: iso(8),
    mttr_hours: 4.9,
    root_cause: "Misconfigured cohort filter",
    summary: "Churn spike traced to cohort filter update.",
    transcript: [
      {
        id: "step-004",
        title: "Trigger anomaly alert",
        detail: "Churn rate up 12% week over week.",
        status: "complete",
        created_at: iso(18),
      },
      {
        id: "step-005",
        title: "Evaluate cohorts",
        detail: "Marketing cohort filter removed trial users.",
        status: "active",
        created_at: iso(10),
      },
    ],
    artifacts: [
      {
        id: "art-003",
        type: "sql",
        title: "Cohort diff",
        content: "SELECT cohort_id, COUNT(*) FROM subscriptions_daily GROUP BY 1;",
      },
    ],
    diagnosis: {
      summary: "Cohort filter change inflated churn definition.",
      confidence: 0.61,
      root_cause: "Analytics cohort rule update",
      recommendations: ["Rollback filter change", "Notify marketing ops"],
    },
  },
  {
    id: "inv-003",
    title: "Warehouse load latency",
    status: "monitoring",
    dataset_id: "ds-003",
    triggered_by: users[1],
    trigger_source: "Great Expectations",
    started_at: iso(30),
    updated_at: iso(6),
    mttr_hours: 6.2,
    summary: "Load latency stabilized after cluster resize.",
    transcript: [
      {
        id: "step-006",
        title: "Latency regression detected",
        detail: "ETL runtime increased 2x.",
        status: "complete",
        created_at: iso(30),
      },
    ],
    artifacts: [
      {
        id: "art-004",
        type: "note",
        title: "Cluster change",
        content: "Scaled compute cluster to restore SLA.",
      },
    ],
    diagnosis: {
      summary: "Cluster autoscaling lag produced queue backlog.",
      confidence: 0.54,
      root_cause: "Autoscaling delay",
      recommendations: ["Tune autoscaling triggers"],
    },
  },
];

export const orgStats: OrgStats = {
  mttr_hours: 4.2,
  mttr_trend: -0.6,
  active_count: 6,
  sla_pct: 98.4,
  monthly_cost: 48200,
  activity_heatmap: Array.from({ length: 90 }, (_, idx) => ({
    date: new Date(Date.now() - (90 - idx) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    count: (idx * 7) % 5,
  })),
};

export const datasetLineage: Record<string, DatasetLineage> = {
  "ds-001": {
    upstream: [
      { id: "raw-payments", name: "raw_payments", direction: "upstream", kind: "table" },
      { id: "fx-rates", name: "fx_rates_daily", direction: "upstream", kind: "table" },
    ],
    downstream: [
      { id: "orders-mart", name: "orders_mart", direction: "downstream", kind: "model" },
      { id: "rev-dashboard", name: "rev_dashboard", direction: "downstream", kind: "view" },
    ],
  },
  "ds-002": {
    upstream: [{ id: "billing", name: "billing_events", direction: "upstream", kind: "table" }],
    downstream: [{ id: "churn-report", name: "churn_report", direction: "downstream", kind: "view" }],
  },
  "ds-003": {
    upstream: [{ id: "etl-metrics", name: "etl_metrics", direction: "upstream", kind: "table" }],
    downstream: [{ id: "sla-board", name: "sla_board", direction: "downstream", kind: "view" }],
  },
};

export const datasetAnomalies: Record<string, DatasetAnomaly[]> = {
  "ds-001": [
    {
      id: "anom-001",
      detected_at: iso(24),
      description: "APAC volume dip below 10th percentile.",
      severity: "high",
    },
  ],
  "ds-002": [
    {
      id: "anom-002",
      detected_at: iso(48),
      description: "Churn spike above baseline.",
      severity: "medium",
    },
  ],
  "ds-003": [
    {
      id: "anom-003",
      detected_at: iso(72),
      description: "Load latency breach.",
      severity: "high",
    },
  ],
};

export const userActivity: Record<string, UserActivity[]> = {
  "user-001": [
    {
      id: "act-001",
      description: "Approved remediation for inv-002",
      activity_type: "approval",
      resource_type: "investigation",
      resource_id: "inv-002",
      timestamp: iso(6),
      created_at: iso(6),
      type: "approval",
    },
    {
      id: "act-002",
      description: "Triggered investigation on orders_fact",
      activity_type: "investigation.triggered",
      resource_type: "investigation",
      resource_id: "inv-003",
      timestamp: iso(12),
      created_at: iso(12),
      type: "investigation",
    },
  ],
};
