# Slack Integration

Get real-time notifications when dataing completes investigations.

---

## What You'll Receive

When an investigation completes, dataing sends a Slack message with:

- **Root cause summary** - What went wrong
- **Confidence score** - How certain the finding is
- **Affected scope** - Tables, columns, time range
- **Recommended actions** - Next steps
- **Link to full report** - Detailed investigation results

---

## Setup

### Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name it "dataing" and select your workspace

### Add Incoming Webhook

1. In your app settings, go to **Incoming Webhooks**
2. Toggle **Activate Incoming Webhooks** to On
3. Click **Add New Webhook to Workspace**
4. Select the channel for notifications
5. Copy the webhook URL

### Configure dataing

=== "Environment Variables"

    ```bash
    export DATAING_NOTIFICATION_PROVIDER=slack
    export DATAING_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR_TEAM_ID/YOUR_BOT_ID/YOUR_WEBHOOK_SECRET
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.notifications.slack import SlackNotifier

    notifier = SlackNotifier(
        webhook_url="https://hooks.slack.com/services/...",
        channel="#data-alerts",  # Optional: override channel
    )
    ```

=== "API"

    ```bash
    curl -X POST https://api.dataing.io/v1/settings/notifications \
      -H "X-API-Key: your-api-key" \
      -d '{
        "provider": "slack",
        "webhook_url": "https://hooks.slack.com/services/..."
      }'
    ```

---

## Message Format

### Investigation Complete

```
🔍 Investigation Complete

*Root Cause:* Mobile app v2.3.1 bug - checkout API not passing user context

*Confidence:* 95%
*Table:* orders
*Column:* user_id
*Anomaly:* NULL rate spike (1% → 15%)
*Affected:* 304 orders from Jan 12-14

*Recommended Actions:*
• Roll back mobile app to v2.3.0
• Fix user context passing in checkout API
• Backfill user_id from session data

<View Full Report | https://app.dataing.io/investigations/inv_abc123>
```

### Investigation Failed

```
⚠️ Investigation Failed

*Table:* orders
*Column:* user_id
*Error:* Circuit breaker tripped - query limit exceeded

*Details:*
Investigation reached the maximum of 50 queries without finding a definitive root cause.

<View Details | https://app.dataing.io/investigations/inv_abc123>
```

---

## Configuration Options

| Option | Required | Description |
|--------|----------|-------------|
| `webhook_url` | Yes | Slack incoming webhook URL |
| `channel` | No | Override default channel |
| `username` | No | Bot display name (default: "dataing") |
| `icon_emoji` | No | Bot icon (default: `:mag:`) |

---

## Filtering Notifications

### By Confidence

Only notify for high-confidence findings:

```python
notifier = SlackNotifier(
    webhook_url="...",
    min_confidence=0.8,  # Only notify if confidence >= 80%
)
```

### By Severity

Only notify for significant anomalies:

```python
notifier = SlackNotifier(
    webhook_url="...",
    min_severity="high",  # low, medium, high, critical
)
```

### By Table

Only notify for specific tables:

```python
notifier = SlackNotifier(
    webhook_url="...",
    table_filter=["orders", "payments", "users"],
)
```

---

## Multiple Channels

Send different notifications to different channels:

```python
# Critical issues to #data-incidents
critical_notifier = SlackNotifier(
    webhook_url="https://hooks.slack.com/services/.../incidents",
    min_severity="critical",
)

# All findings to #data-quality
general_notifier = SlackNotifier(
    webhook_url="https://hooks.slack.com/services/.../quality",
)
```

---

## Troubleshooting

### "Webhook URL invalid"

Check that:

- URL starts with `https://hooks.slack.com/services/`
- Webhook is not revoked in Slack app settings
- App is installed in the workspace

### "Channel not found"

If using channel override:

- Ensure the channel exists
- Invite the app to the channel: `/invite @dataing`

### Messages Not Appearing

Check:

- Slack app has permission to post to the channel
- Webhook is not rate-limited
- Network allows outbound HTTPS to Slack

---

## Learn More

<div class="grid cards" markdown>

-   :material-hexagon-outline: **[Architecture](../../architecture.md)**

    ---

    System overview and design

-   :material-shield: **[Security](../../security/data-privacy.md)**

    ---

    Data privacy and protection

-   :material-rocket-launch: **[Quickstart](../../quickstart.md)**

    ---

    Get started in 5 minutes

</div>
