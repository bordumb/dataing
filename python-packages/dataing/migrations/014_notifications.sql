-- In-app notifications for real-time user alerts
-- Migration 014: Notifications

-- Notifications table (one row per event, broadcast to tenant)
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,  -- 'investigation_completed', 'investigation_failed', etc.
    title TEXT NOT NULL,
    body TEXT,
    resource_kind VARCHAR(50),  -- 'investigation', 'approval', etc.
    resource_id UUID,           -- ID of the linked resource
    severity VARCHAR(20) DEFAULT 'info',  -- 'info', 'success', 'warning', 'error'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-user read state (join table for tracking which users have read which notifications)
CREATE TABLE notification_reads (
    notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    read_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (notification_id, user_id)
);

-- Indexes for efficient queries
-- Composite index for cursor pagination (created_at DESC, id DESC)
CREATE INDEX idx_notifications_tenant_cursor ON notifications(tenant_id, created_at DESC, id DESC);
CREATE INDEX idx_notifications_tenant_type ON notifications(tenant_id, type);
CREATE INDEX idx_notification_reads_user ON notification_reads(user_id, notification_id);
