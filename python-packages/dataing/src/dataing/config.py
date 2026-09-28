"""Backend settings loaded from the environment.

The API and the Temporal worker both read these, so they live outside either entrypoint.
"""

import os


class Settings:
    """Application settings loaded from environment."""

    def __init__(self) -> None:
        """Load settings from environment variables."""
        self.database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/dataing")
        self.app_database_url = os.getenv("APP_DATABASE_URL", self.database_url)
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

        # Issue chat agent (docs/specs/0001_issue_chat.md): model and effort per route.
        # Speed comes from low effort, not a smaller model; an empty effort leaves
        # the model's default.
        self.chat_agent_model = os.getenv("CHAT_AGENT_MODEL", "claude-opus-5-5")
        self.chat_agent_effort = os.getenv("CHAT_AGENT_EFFORT", "low")
        self.chat_brief_effort = os.getenv("CHAT_BRIEF_EFFORT", "medium")

        # Circuit breaker settings
        self.max_total_queries = int(os.getenv("MAX_TOTAL_QUERIES", "50"))
        self.max_queries_per_hypothesis = int(os.getenv("MAX_QUERIES_PER_HYPOTHESIS", "5"))
        self.max_retries_per_hypothesis = int(os.getenv("MAX_RETRIES_PER_HYPOTHESIS", "2"))

        # SMTP settings for email notifications
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from_email = os.getenv("SMTP_FROM_EMAIL", "noreply@dataing.io")
        self.smtp_from_name = os.getenv("SMTP_FROM_NAME", "Dataing")
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

        # Frontend URL for building links in emails
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

        # Password recovery settings
        # "auto" = email if SMTP configured, else console
        # "email" = force email (fails if no SMTP)
        # "console" = force console (prints reset link to stdout)
        # "admin_contact" = show admin contact info (for SSO orgs)
        self.password_recovery_type = os.getenv("PASSWORD_RECOVERY_TYPE", "auto")
        self.admin_email = os.getenv("ADMIN_EMAIL", "")

        # Redis settings for job queue
        self.redis_url = os.getenv("REDIS_URL", "")
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = os.getenv("REDIS_PASSWORD", "")
        self.redis_db = int(os.getenv("REDIS_DB", "0"))

        # Temporal settings for durable workflow execution
        self.TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
        self.TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
        self.TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "investigations")

        # Investigation engine: "temporal" (durable workflow execution)
        self.INVESTIGATION_ENGINE = os.getenv("INVESTIGATION_ENGINE", "temporal")

        # GitHub OAuth settings for git integration
        self.github_client_id = os.getenv("GITHUB_CLIENT_ID", "")
        self.github_client_secret = os.getenv("GITHUB_CLIENT_SECRET", "")


settings = Settings()
