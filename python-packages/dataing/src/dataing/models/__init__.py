"""SQLAlchemy models for the application database."""

from dataing.models.api_key import ApiKey
from dataing.models.base import BaseModel
from dataing.models.code_change import CodeChange
from dataing.models.credentials import QueryAuditLog, UserDatasourceCredentials
from dataing.models.data_source import DataSource, DataSourceType
from dataing.models.dataset_repo_mapping import DatasetRepoMapping
from dataing.models.git_repository import GitRepository
from dataing.models.investigation import Investigation, InvestigationStatus
from dataing.models.issue import (
    Issue,
    IssueApprovalStatus,
    IssueAuthorType,
    IssueEvent,
    IssueEventType,
    IssueExecutionProfile,
    IssueInvestigationRun,
    IssuePriority,
    IssueRelationship,
    IssueRelationshipType,
    IssueSeverity,
    IssueStatus,
    IssueTriggerType,
    IssueWatcher,
    SLABreachNotification,
    SLAPolicy,
    SLAType,
)
from dataing.models.notification import Notification, NotificationRead, NotificationSeverity
from dataing.models.tenant import Tenant
from dataing.models.user import User
from dataing.models.webhook import Webhook

__all__ = [
    "BaseModel",
    "Tenant",
    "User",
    "ApiKey",
    "CodeChange",
    "DataSource",
    "DataSourceType",
    "DatasetRepoMapping",
    "GitRepository",
    "QueryAuditLog",
    "UserDatasourceCredentials",
    "Investigation",
    "InvestigationStatus",
    "Issue",
    "IssueApprovalStatus",
    "IssueAuthorType",
    "IssueEvent",
    "IssueEventType",
    "IssueExecutionProfile",
    "IssueInvestigationRun",
    "IssuePriority",
    "IssueRelationship",
    "IssueRelationshipType",
    "IssueSeverity",
    "IssueStatus",
    "IssueTriggerType",
    "IssueWatcher",
    "SLABreachNotification",
    "SLAPolicy",
    "SLAType",
    "Webhook",
    "Notification",
    "NotificationRead",
    "NotificationSeverity",
]
