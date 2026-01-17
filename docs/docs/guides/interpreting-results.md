# Interpreting Investigation Results

This guide helps you understand what dataing finds and how to act on it.

---

## Investigation Output Overview

When an investigation completes, you'll see:

| Section | What It Contains |
|---------|------------------|
| **Root Cause** | The most likely explanation for the anomaly |
| **Confidence Score** | How certain the system is (0.0 - 1.0) |
| **Evidence** | SQL queries and results that support the finding |
| **Recommendations** | Suggested actions to fix or investigate further |

---

## Understanding Confidence Scores

The confidence score indicates how strongly the evidence supports the conclusion.

| Score | Meaning | Action |
|-------|---------|--------|
| **0.90 - 1.0** | High confidence | Strong evidence, likely correct. Act on recommendations. |
| **0.70 - 0.89** | Moderate confidence | Good evidence, worth investigating. Verify before acting. |
| **0.50 - 0.69** | Low confidence | Weak or conflicting evidence. Manual investigation needed. |
| **Below 0.50** | Very low confidence | Insufficient evidence. Add more context or lineage data. |

!!! tip "Confidence is not certainty"
    Even high-confidence findings should be verified with your domain knowledge. The system can identify patterns but doesn't understand your business context.

---

## Reading the Evidence

Each piece of evidence includes:

### The Query

```sql
-- Example query testing "upstream ETL failure" hypothesis
SELECT date, count(*) as row_count
FROM analytics.orders
WHERE date >= '2026-01-01'
GROUP BY date
ORDER BY date
```

**What to check:**
- Does the date range match the anomaly period?
- Are the right tables being queried?
- Is the aggregation appropriate?

### The Results

| date | row_count |
|------|-----------|
| 2026-01-08 | 15,234 |
| 2026-01-09 | 15,102 |
| 2026-01-10 | 2,341 |  ← Drop detected
| 2026-01-11 | 15,456 |

**What to check:**
- Does the pattern match what the system claims?
- Are there outliers that might explain the result differently?

### The Interpretation

> "Row count dropped 85% on 2026-01-10, consistent with ETL pipeline failure. Recovery on 2026-01-11 suggests a single-day issue rather than ongoing problem."

---

## What Makes Strong Evidence?

Strong evidence typically has:

| Indicator | Why It Matters |
|-----------|----------------|
| **Multiple signals** | Three queries pointing to the same cause is stronger than one |
| **Clear before/after** | Visible change at the anomaly timestamp |
| **Upstream correlation** | Issue traces back through lineage |
| **Consistent pattern** | Evidence doesn't contradict itself |

### Example: Strong Evidence

> **Finding:** "NULL rate spike caused by schema change in upstream `raw.customers` table"
>
> **Evidence:**
> 1. Query shows NULL rate jumped from 0.1% to 15% on Jan 10
> 2. Lineage trace shows `analytics.orders` depends on `raw.customers`
> 3. Schema diff shows `customer_id` column was made nullable on Jan 10
> 4. NULL values in `orders` trace to missing `customer_id` in `customers`
>
> **Confidence:** 0.94

This is strong because:
- Multiple independent queries
- Clear timestamp correlation
- Lineage explains the connection
- Schema change is verifiable

---

## What Makes Weak Evidence?

Be cautious when you see:

| Indicator | Why It's Weak |
|-----------|---------------|
| **Single data point** | One query isn't enough to confirm a pattern |
| **Ambiguous pattern** | Results could support multiple hypotheses |
| **Missing lineage** | Can't trace upstream relationships |
| **Conflicting signals** | Evidence points in different directions |

### Example: Weak Evidence

> **Finding:** "Possible data duplication from merge conflict"
>
> **Evidence:**
> 1. Query shows row count increased 12% on Jan 10
>
> **Confidence:** 0.45

This is weak because:
- Only one query
- 12% increase could be normal growth
- No lineage to trace source
- No duplication check performed

---

## When to Trust Recommendations

### Trust recommendations when:

- Confidence score is above 0.70
- Evidence clearly supports the finding
- The suggested action is reversible or low-risk
- You can verify the fix quickly

### Verify before acting when:

- Confidence is below 0.70
- Evidence seems circumstantial
- Action is irreversible (deleting data, schema changes)
- The finding contradicts your domain knowledge

---

## Common Anomaly Patterns

### Volume Drop

**Symptoms:** Row count suddenly decreases
**Common causes:**
- ETL pipeline failure
- Source system outage
- Filter condition change
- Partition issues

**What to check:** Upstream job logs, source system status

### NULL Spike

**Symptoms:** NULL rate increases dramatically
**Common causes:**
- Schema change (column made nullable)
- Join condition failure
- Source data quality issue
- Backfill with incomplete data

**What to check:** Recent schema changes, join conditions

### Duplicate Records

**Symptoms:** Unexpected row count increase, repeated values
**Common causes:**
- Merge/upsert failure
- Multiple pipeline runs
- Missing deduplication
- Primary key constraint removed

**What to check:** Pipeline run history, primary key constraints

### Late-Arriving Data

**Symptoms:** Historical data changes after fact
**Common causes:**
- Backfill operations
- Reprocessing jobs
- Time zone issues
- Slowly changing dimensions

**What to check:** Pipeline schedules, backfill logs

---

## Improving Investigation Quality

If investigations consistently produce low-confidence results:

### Add More Context

- **Connect lineage providers** (dbt, DataHub) to trace upstream dependencies
- **Provide schema descriptions** so the system understands column semantics
- **Configure sample data access** for pattern detection

### Refine Alert Descriptions

Better alert descriptions lead to better investigations:

| Weak Alert | Strong Alert |
|------------|--------------|
| "Data looks wrong" | "NULL rate in orders.customer_id increased from 0.1% to 15% on 2026-01-10" |
| "ETL failed" | "Daily orders pipeline produced 85% fewer rows than expected on 2026-01-10" |

### Check Data Access

Ensure dataing has:
- Read access to relevant tables
- Ability to query historical data
- Access to upstream tables (for lineage tracing)

---

## Getting Help

If you're unsure how to interpret results:

1. **Check the queries** - Verify they're querying the right data
2. **Review the lineage** - Trace upstream dependencies
3. **Compare to known issues** - Does this match a past incident?
4. **Ask your data team** - Domain experts can validate findings

---

## See Also

- [How Investigations Work](../concepts/investigations.md) - Technical overview
- [Safety & Guardrails](../concepts/guardrails.md) - How queries are validated
- [Data Privacy](../security/data-privacy.md) - What data is accessed
