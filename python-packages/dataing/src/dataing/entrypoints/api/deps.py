"""Dependency injection and application lifespan management."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import Request

from dataing.adapters.audit import AuditRepository
from dataing.adapters.auth.recovery_admin import AdminContactRecoveryAdapter
from dataing.adapters.auth.recovery_console import ConsoleRecoveryAdapter
from dataing.adapters.auth.recovery_email import EmailPasswordRecoveryAdapter
from dataing.adapters.context import ContextEngine
from dataing.adapters.datasource import BaseAdapter, get_registry
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.investigation_repository import PostgresInvestigationRepository
from dataing.adapters.entitlements import DatabaseEntitlementsAdapter
from dataing.adapters.investigation.pattern_adapter import InMemoryPatternRepository
from dataing.adapters.investigation_feedback import InvestigationFeedbackAdapter
from dataing.adapters.lineage import BaseLineageAdapter, LineageAdapter, get_lineage_registry
from dataing.adapters.notifications.email import EmailConfig, EmailNotifier
from dataing.agents import AgentClient
from dataing.core.auth.recovery import PasswordRecoveryAdapter
from dataing.core.investigation.collaboration import CollaborationService
from dataing.core.investigation.service import InvestigationService
from dataing.core.json_utils import to_json_string
from dataing.services.usage import UsageTracker

if TYPE_CHECKING:
    from fastapi import FastAPI

    from dataing.services.investigation import InvestigationStarterService

logger = logging.getLogger(__name__)


class Settings:
    """Application settings loaded from environment."""

    def __init__(self) -> None:
        """Load settings from environment variables."""
        self.database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/dataing")
        self.app_database_url = os.getenv("APP_DATABASE_URL", self.database_url)
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan - setup and teardown.

    This context manager handles:
    - Database connection pool setup
    - LLM client initialization
    - Orchestrator configuration
    """
    # Setup application database
    app_db = AppDatabase(settings.app_database_url)
    await app_db.connect()

    # Create audit repository
    audit_repo = AuditRepository(pool=app_db.pool)
    app.state.audit_repo = audit_repo

    # Create entitlements adapter for plan-based feature gating
    entitlements_adapter = DatabaseEntitlementsAdapter(pool=app_db.pool)
    app.state.entitlements_adapter = entitlements_adapter

    llm = AgentClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
    )

    # Create context engine
    context_engine = ContextEngine()

    # Initialize investigation feedback adapter
    feedback_adapter = InvestigationFeedbackAdapter(db=app_db)

    # Initialize usage tracker
    usage_tracker = UsageTracker(db=app_db)

    # Initialize unified investigation service (v2 API)
    investigation_repository = PostgresInvestigationRepository(db=app_db)
    collaboration_service = CollaborationService(repository=investigation_repository)
    pattern_repository = InMemoryPatternRepository()
    investigation_service = InvestigationService(
        repository=investigation_repository,
        collaboration=collaboration_service,
        agent_client=llm,
        context_engine=context_engine,
        pattern_repository=pattern_repository,
        usage_tracker=usage_tracker,
        app_db=app_db,
    )

    # Initialize email notifier (optional, needed for email recovery)
    email_notifier: EmailNotifier | None = None
    if settings.smtp_host:
        email_config = EmailConfig(
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user or None,
            smtp_password=settings.smtp_password or None,
            from_email=settings.smtp_from_email,
            from_name=settings.smtp_from_name,
            use_tls=settings.smtp_use_tls,
        )
        email_notifier = EmailNotifier(email_config)
        logger.info("Email notifier initialized")

    # Initialize password recovery adapter based on configuration
    recovery_adapter: PasswordRecoveryAdapter
    recovery_type = settings.password_recovery_type.lower()

    if recovery_type == "auto":
        # Auto-select: email if SMTP configured, else console
        if settings.smtp_host and email_notifier:
            recovery_adapter = EmailPasswordRecoveryAdapter(
                email_notifier=email_notifier,
                frontend_url=settings.frontend_url,
            )
            logger.info("Using email recovery adapter (SMTP configured)")
        else:
            recovery_adapter = ConsoleRecoveryAdapter(
                frontend_url=settings.frontend_url,
            )
            logger.info("Using console recovery adapter (no SMTP, demo mode)")

    elif recovery_type == "email":
        # Force email - fail if no SMTP
        if not settings.smtp_host or not email_notifier:
            raise RuntimeError("PASSWORD_RECOVERY_TYPE=email but SMTP_HOST not configured")
        recovery_adapter = EmailPasswordRecoveryAdapter(
            email_notifier=email_notifier,
            frontend_url=settings.frontend_url,
        )
        logger.info("Using email recovery adapter (forced)")

    elif recovery_type == "console":
        # Force console
        recovery_adapter = ConsoleRecoveryAdapter(
            frontend_url=settings.frontend_url,
        )
        logger.info("Using console recovery adapter (forced)")

    elif recovery_type == "admin_contact":
        # Admin contact for SSO orgs
        recovery_adapter = AdminContactRecoveryAdapter(
            admin_email=settings.admin_email or None,
        )
        logger.info("Using admin contact recovery adapter")

    else:
        raise RuntimeError(
            f"Invalid PASSWORD_RECOVERY_TYPE: {recovery_type}. "
            "Must be one of: auto, email, console, admin_contact"
        )

    # Store in app state
    app.state.app_db = app_db
    app.state.llm = llm
    app.state.context_engine = context_engine
    app.state.feedback_adapter = feedback_adapter
    app.state.usage_tracker = usage_tracker
    app.state.investigation_service = investigation_service  # Unified investigation service (v2)
    app.state.email_notifier = email_notifier
    app.state.recovery_adapter = recovery_adapter
    app.state.frontend_url = settings.frontend_url
    # Check DATADR_ENCRYPTION_KEY first (used by demo), then ENCRYPTION_KEY
    app.state.encryption_key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")

    # Cache for active adapters (tenant_id:datasource_id -> adapter)
    adapter_cache: dict[str, BaseAdapter] = {}
    app.state.adapter_cache = adapter_cache

    investigations_store: dict[str, dict[str, Any]] = {}
    app.state.investigations = investigations_store

    # Initialize Temporal client for durable workflow execution
    from dataing.temporal.client import TemporalInvestigationClient

    try:
        temporal_client = await TemporalInvestigationClient.connect(
            host=settings.TEMPORAL_HOST,
            namespace=settings.TEMPORAL_NAMESPACE,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
        app.state.temporal_client = temporal_client
        logger.info(
            f"Temporal client connected: host={settings.TEMPORAL_HOST}, "
            f"namespace={settings.TEMPORAL_NAMESPACE}, "
            f"task_queue={settings.TEMPORAL_TASK_QUEUE}"
        )
    except Exception as e:
        logger.error(
            f"Failed to connect Temporal client: {e}. "
            "Investigations require Temporal. Please check TEMPORAL_HOST configuration."
        )
        raise RuntimeError(
            f"Temporal client connection failed: {e}. "
            f"Configure TEMPORAL_HOST (current: {settings.TEMPORAL_HOST})"
        ) from e

    # Demo mode: seed demo data
    demo_mode = os.getenv("DATADR_DEMO_MODE", "").lower()
    print(f"[DEBUG] DATADR_DEMO_MODE={demo_mode}", flush=True)
    if demo_mode == "true":
        print("[DEBUG] Running in DEMO MODE - seeding demo data", flush=True)
        await _seed_demo_data(app_db)
        # Re-read encryption key in case _seed_demo_data generated one
        app.state.encryption_key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")

    yield

    # Teardown - close all cached adapters
    for cache_key, adapter in app.state.adapter_cache.items():
        try:
            await adapter.disconnect()
            logger.debug(f"adapter_closed: {cache_key}")
        except Exception as e:
            logger.warning(f"adapter_close_failed: {cache_key}, error={e}")

    await app_db.close()


async def _seed_demo_data(app_db: AppDatabase) -> None:
    """Seed demo data into the application database.

    This is called when DATADR_DEMO_MODE=true.
    Creates a demo tenant, API key, and data source pointing to fixtures.
    """
    import hashlib
    from uuid import UUID

    from cryptography.fernet import Fernet

    # Demo IDs - stable UUIDs for idempotent seeding
    DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
    DEMO_API_KEY_ID = UUID("00000000-0000-0000-0000-000000000002")
    DEMO_DATASOURCE_ID = UUID("00000000-0000-0000-0000-000000000003")

    # Demo API key value - pragma: allowlist secret
    DEMO_API_KEY_VALUE = "dd_demo_12345"  # pragma: allowlist secret
    DEMO_API_KEY_PREFIX = "dd_demo_"  # pragma: allowlist secret
    DEMO_API_KEY_HASH = hashlib.sha256(DEMO_API_KEY_VALUE.encode()).hexdigest()

    # Check if already seeded
    existing = await app_db.fetch_one(
        "SELECT id FROM tenants WHERE id = $1",
        DEMO_TENANT_ID,
    )

    if existing:
        logger.info("Demo data already seeded, skipping")
        return

    logger.info("Seeding demo data...")

    # Create demo tenant
    await app_db.execute(
        """INSERT INTO tenants (id, name, slug, settings)
           VALUES ($1, $2, $3, $4)""",
        DEMO_TENANT_ID,
        "Demo Account",
        "demo",
        to_json_string({"plan_tier": "enterprise"}),
    )

    # Create demo API key
    await app_db.execute(
        """INSERT INTO api_keys (id, tenant_id, key_hash, key_prefix, name, scopes, is_active)
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        DEMO_API_KEY_ID,
        DEMO_TENANT_ID,
        DEMO_API_KEY_HASH,
        DEMO_API_KEY_PREFIX,
        "Demo API Key",
        to_json_string(["read", "write", "admin"]),
        True,
    )

    # Create demo data source (DuckDB pointing to fixtures)
    fixture_path = os.getenv("DATADR_FIXTURE_PATH", "./demo/fixtures/null_spike")
    # Check DATADR_ENCRYPTION_KEY first (used by demo), then ENCRYPTION_KEY
    encryption_key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")
    if not encryption_key:
        encryption_key = Fernet.generate_key().decode()
        os.environ["DATADR_ENCRYPTION_KEY"] = encryption_key

    connection_config = {
        "source_type": "directory",
        "path": fixture_path,
        "read_only": True,
    }
    f = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
    encrypted_config = f.encrypt(to_json_string(connection_config).encode()).decode()

    await app_db.execute(
        """INSERT INTO data_sources
            (id, tenant_id, name, type, connection_config_encrypted,
            is_default, is_active, last_health_check_status)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
        DEMO_DATASOURCE_ID,
        DEMO_TENANT_ID,
        "E-Commerce Demo",
        "duckdb",
        encrypted_config,
        True,
        True,
        "healthy",
    )

    logger.info("Demo data seeded successfully")
    logger.info(f"  API Key: {DEMO_API_KEY_VALUE}")
    logger.info(f"  Data Source: E-Commerce Demo (path: {fixture_path})")


def get_investigations(request: Request) -> dict[str, dict[str, Any]]:
    """Get the investigations store from app state.

    Args:
        request: The current request.

    Returns:
        Dictionary of investigation states.
    """
    investigations: dict[str, dict[str, Any]] = request.app.state.investigations
    return investigations


def get_app_db(request: Request) -> AppDatabase:
    """Get the application database from app state.

    Args:
        request: The current request.

    Returns:
        The configured AppDatabase.
    """
    app_db: AppDatabase = request.app.state.app_db
    return app_db


async def get_tenant_adapter(
    request: Request,
    tenant_id: UUID,
    data_source_id: UUID | None = None,
) -> BaseAdapter:
    """Get or create a data source adapter for a tenant.

    This function replaces DatabaseContext, using the AdapterRegistry
    pattern instead. It caches adapters for reuse within the app lifecycle.

    Args:
        request: The current request (for accessing app state).
        tenant_id: The tenant's UUID.
        data_source_id: Optional specific data source ID. If not provided,
                       uses the tenant's default data source.

    Returns:
        A connected BaseAdapter for the data source.

    Raises:
        ValueError: If data source not found or type not supported.
        RuntimeError: If decryption or connection fails.
    """
    app_db: AppDatabase = request.app.state.app_db
    adapter_cache: dict[str, BaseAdapter] = request.app.state.adapter_cache
    encryption_key: str | None = request.app.state.encryption_key

    # Get data source configuration
    if data_source_id:
        ds = await app_db.get_data_source(data_source_id, tenant_id)
        if not ds:
            raise ValueError(f"Data source {data_source_id} not found for tenant {tenant_id}")
    else:
        # Get default data source
        data_sources = await app_db.list_data_sources(tenant_id)
        active_sources = [d for d in data_sources if d.get("is_active", True)]
        if not active_sources:
            raise ValueError(f"No active data sources found for tenant {tenant_id}")
        ds = active_sources[0]
        data_source_id = ds["id"]

    # Check cache
    cache_key = f"{tenant_id}:{data_source_id}"
    if cache_key in adapter_cache:
        logger.debug(f"adapter_cache_hit: {cache_key}")
        return adapter_cache[cache_key]

    # Decrypt connection config
    if not encryption_key:
        raise RuntimeError(
            "ENCRYPTION_KEY not set - check DATADR_ENCRYPTION_KEY or ENCRYPTION_KEY env vars"
        )

    encrypted_config = ds.get("connection_config_encrypted", "")
    try:
        f = Fernet(encryption_key.encode())
        decrypted = f.decrypt(encrypted_config.encode()).decode()
        config: dict[str, Any] = json.loads(decrypted)
    except Exception as e:
        raise RuntimeError(f"Failed to decrypt connection config: {e}") from e

    # Create adapter using registry
    registry = get_registry()
    ds_type = ds["type"]

    try:
        adapter = registry.create(ds_type, config)
        await adapter.connect()
    except Exception as e:
        raise RuntimeError(f"Failed to create/connect adapter for {ds_type}: {e}") from e

    # Cache for reuse
    adapter_cache[cache_key] = adapter
    logger.info(f"adapter_created: type={ds_type}, name={ds.get('name')}, key={cache_key}")

    return adapter


async def get_default_tenant_adapter(request: Request, tenant_id: UUID) -> BaseAdapter:
    """Get the default data source adapter for a tenant.

    Convenience wrapper around get_tenant_adapter that uses the default
    data source.

    Args:
        request: The current request.
        tenant_id: The tenant's UUID.

    Returns:
        A connected BaseAdapter for the tenant's default data source.
    """
    return await get_tenant_adapter(request, tenant_id)


async def resolve_datasource_id(
    request: Request,
    tenant_id: UUID,
    explicit_id: UUID | None = None,
    asset_id: UUID | None = None,
    session_default: UUID | None = None,
) -> UUID:
    """Resolve the datasource ID following documented precedence rules.

    Precedence order (highest to lowest):
    1. Explicit `datasource_id` in request
    2. Asset-level `datasource_id` (from URN or attachment)
    3. Session/context `default_datasource_id`
    4. Tenant's single datasource (if only one exists)
    5. 409 Conflict if ambiguous

    Args:
        request: The current request (for accessing app state).
        tenant_id: The tenant's UUID.
        explicit_id: Explicit datasource ID from request.
        asset_id: Asset-level datasource binding.
        session_default: Session/context default datasource.

    Returns:
        The resolved datasource UUID.

    Raises:
        ValueError: If datasource not found or ambiguous.
    """
    app_db: AppDatabase = request.app.state.app_db

    # 1. Explicit always wins
    if explicit_id:
        ds = await app_db.get_data_source(explicit_id, tenant_id)
        if not ds:
            raise ValueError(f"Datasource {explicit_id} not found for tenant {tenant_id}")
        return explicit_id

    # 2. Asset-level binding
    if asset_id:
        ds = await app_db.get_data_source(asset_id, tenant_id)
        if not ds:
            raise ValueError(f"Datasource {asset_id} not found for tenant {tenant_id}")
        return asset_id

    # 3. Session default
    if session_default:
        ds = await app_db.get_data_source(session_default, tenant_id)
        if not ds:
            raise ValueError(f"Datasource {session_default} not found for tenant {tenant_id}")
        return session_default

    # 4. Single datasource for tenant
    data_sources = await app_db.list_data_sources(tenant_id)
    active_sources = [d for d in data_sources if d.get("is_active", True)]

    if not active_sources:
        raise ValueError(f"No active datasources found for tenant {tenant_id}")

    if len(active_sources) == 1:
        result: UUID = active_sources[0]["id"]
        return result

    # 5. Ambiguous - raise with available options
    available = [
        {
            "id": str(ds["id"]),
            "name": ds.get("name", "Unknown"),
            "platform": ds.get("platform", "Unknown"),
            "host": ds.get("host"),
        }
        for ds in active_sources
    ]
    raise ValueError(
        f"ambiguous_datasource:Multiple datasources available. "
        f"Specify datasource_id or use session default. "
        f"Available: {available}"
    )


async def get_tenant_lineage_adapter(
    request: Request,
    tenant_id: UUID,
) -> LineageAdapter | None:
    """Get a lineage adapter for a tenant based on their configuration.

    Creates a lineage adapter (or composite adapter for multiple providers)
    based on the tenant's lineage_providers settings.

    Args:
        request: The current request (for accessing app state).
        tenant_id: The tenant's UUID.

    Returns:
        A LineageAdapter if configured, None if no lineage providers.
    """
    app_db: AppDatabase = request.app.state.app_db

    # Get tenant settings
    tenant = await app_db.get_tenant(tenant_id)
    if not tenant:
        logger.warning(f"Tenant {tenant_id} not found for lineage adapter")
        return None

    settings = tenant.get("settings", {})
    if isinstance(settings, str):
        settings = json.loads(settings)

    lineage_providers = settings.get("lineage_providers", [])
    if not lineage_providers:
        logger.debug(f"No lineage providers configured for tenant {tenant_id}")
        return None

    registry = get_lineage_registry()

    # Single provider: create directly
    if len(lineage_providers) == 1:
        provider_config = lineage_providers[0]
        try:
            adapter: BaseLineageAdapter = registry.create(
                provider_config["provider"],
                provider_config.get("config", {}),
            )
            logger.info(
                f"Created lineage adapter for tenant {tenant_id}: {provider_config['provider']}"
            )
            return adapter
        except Exception as e:
            logger.error(f"Failed to create lineage adapter for tenant {tenant_id}: {e}")
            return None

    # Multiple providers: create composite adapter
    try:
        adapter = registry.create_composite(lineage_providers)
        logger.info(
            f"Created composite lineage adapter for tenant {tenant_id} with "
            f"{len(lineage_providers)} providers"
        )
        return adapter
    except Exception as e:
        logger.error(f"Failed to create composite lineage adapter for tenant {tenant_id}: {e}")
        return None


def get_context_engine_for_tenant(
    request: Request,
    lineage_adapter: LineageAdapter | None = None,
) -> ContextEngine:
    """Get a context engine with optional lineage adapter.

    Args:
        request: The current request.
        lineage_adapter: Optional lineage adapter for the tenant.

    Returns:
        A ContextEngine configured with the lineage adapter.
    """
    # Get base context engine components from app state
    base_engine: ContextEngine = request.app.state.context_engine

    # If no lineage adapter, return the base engine
    if lineage_adapter is None:
        return base_engine

    # Create a new context engine with the lineage adapter
    return ContextEngine(
        schema_builder=base_engine.schema_builder,
        anomaly_ctx=base_engine.anomaly_ctx,
        correlation_ctx=base_engine.correlation_ctx,
        lineage_adapter=lineage_adapter,
    )


def get_feedback_adapter(request: Request) -> InvestigationFeedbackAdapter:
    """Get InvestigationFeedbackAdapter from app state.

    Args:
        request: The current request.

    Returns:
        The configured InvestigationFeedbackAdapter.
    """
    feedback_adapter: InvestigationFeedbackAdapter = request.app.state.feedback_adapter
    return feedback_adapter


def get_recovery_adapter(request: Request) -> PasswordRecoveryAdapter:
    """Get password recovery adapter from app state.

    The adapter is always available - in demo mode it uses ConsoleRecoveryAdapter,
    in production it uses EmailPasswordRecoveryAdapter, etc.

    Args:
        request: The current request.

    Returns:
        The configured password recovery adapter.
    """
    adapter: PasswordRecoveryAdapter = request.app.state.recovery_adapter
    return adapter


def get_frontend_url(request: Request) -> str:
    """Get frontend URL from app state.

    Args:
        request: The current request.

    Returns:
        The frontend URL for building links.
    """
    frontend_url: str = request.app.state.frontend_url
    return frontend_url


def get_entitlements_adapter(request: Request) -> DatabaseEntitlementsAdapter:
    """Get entitlements adapter from app state.

    Args:
        request: The current request.

    Returns:
        The configured entitlements adapter for plan-based feature gating.
    """
    adapter: DatabaseEntitlementsAdapter = request.app.state.entitlements_adapter
    return adapter


def get_usage_tracker(request: Request) -> UsageTracker:
    """Get usage tracker from app state.

    Args:
        request: The current request.

    Returns:
        The configured UsageTracker for tracking usage metrics.
    """
    tracker: UsageTracker = request.app.state.usage_tracker
    return tracker


def get_investigation_starter(request: Request) -> InvestigationStarterService:
    """Get investigation starter service from app state.

    This service provides a centralized way to start Temporal investigations,
    ensuring consistent behavior across all entry points.

    Args:
        request: The current request.

    Returns:
        An InvestigationStarterService configured with db and temporal client.
    """
    from dataing.services.investigation import InvestigationStarterService
    from dataing.temporal.client import TemporalInvestigationClient

    app_db: AppDatabase = request.app.state.app_db
    temporal_client: TemporalInvestigationClient | None = getattr(
        request.app.state, "temporal_client", None
    )
    return InvestigationStarterService(db=app_db, temporal_client=temporal_client)
