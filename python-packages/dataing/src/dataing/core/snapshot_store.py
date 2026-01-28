"""Snapshot storage protocol and implementations.

Provides interfaces and implementations for storing investigation snapshots
to various backends (S3, GCS, local filesystem).
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dataing.core.snapshot import InvestigationSnapshot


@runtime_checkable
class SnapshotStore(Protocol):
    """Interface for snapshot storage backends.

    Implementations must provide:
    - Async write with path generation
    - Optional compression support
    - Content-addressable storage paths

    Storage path format: {tenant_id}/snapshots/{investigation_id}/{checkpoint}.snapshot
    """

    @abstractmethod
    async def store(
        self,
        snapshot: InvestigationSnapshot,
        tenant_id: str,
    ) -> str:
        """Store a snapshot and return the storage path.

        Args:
            snapshot: The investigation snapshot to store.
            tenant_id: Tenant identifier for path namespacing.

        Returns:
            Storage path where the snapshot was written.

        Raises:
            SnapshotStoreError: If storage fails.
        """
        ...

    @abstractmethod
    async def retrieve(
        self,
        path: str,
    ) -> InvestigationSnapshot:
        """Retrieve a snapshot from storage.

        Args:
            path: Storage path returned by store().

        Returns:
            The deserialized InvestigationSnapshot.

        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist.
            SnapshotStoreError: If retrieval fails.
        """
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a snapshot exists at the given path.

        Args:
            path: Storage path to check.

        Returns:
            True if snapshot exists, False otherwise.
        """
        ...


class SnapshotStoreError(Exception):
    """Base exception for snapshot storage errors."""


class SnapshotNotFoundError(SnapshotStoreError):
    """Raised when a snapshot doesn't exist at the given path."""


class LocalSnapshotStore:
    """Local filesystem implementation of SnapshotStore.

    Stores snapshots as JSON files in a local directory structure.
    Useful for development, testing, and single-node deployments.
    """

    def __init__(self, base_path: str | Path) -> None:
        """Initialize local snapshot store.

        Args:
            base_path: Base directory for snapshot storage.
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _build_path(self, tenant_id: str, snapshot: InvestigationSnapshot) -> Path:
        """Build storage path for a snapshot.

        Args:
            tenant_id: Tenant identifier.
            snapshot: The snapshot to store.

        Returns:
            Full path for the snapshot file.
        """
        return (
            self.base_path
            / tenant_id
            / "snapshots"
            / str(snapshot.investigation_id)
            / f"{snapshot.checkpoint.value}.snapshot"
        )

    async def store(
        self,
        snapshot: InvestigationSnapshot,
        tenant_id: str,
    ) -> str:
        """Store a snapshot to local filesystem.

        Args:
            snapshot: The investigation snapshot to store.
            tenant_id: Tenant identifier for path namespacing.

        Returns:
            Storage path where the snapshot was written.
        """
        import json

        path = self._build_path(tenant_id, snapshot)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize snapshot to JSON
        try:
            data = snapshot.model_dump(mode="json")
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            raise SnapshotStoreError(f"Failed to store snapshot: {e}") from e

        return str(path)

    async def retrieve(
        self,
        path: str,
    ) -> InvestigationSnapshot:
        """Retrieve a snapshot from local filesystem.

        Args:
            path: Storage path to the snapshot file.

        Returns:
            The deserialized InvestigationSnapshot.
        """
        import json

        from dataing.core.snapshot import InvestigationSnapshot

        file_path = Path(path)
        if not file_path.exists():
            raise SnapshotNotFoundError(f"Snapshot not found: {path}")

        try:
            with open(file_path) as f:
                data = json.load(f)
            return InvestigationSnapshot.model_validate(data)
        except Exception as e:
            raise SnapshotStoreError(f"Failed to retrieve snapshot: {e}") from e

    async def exists(self, path: str) -> bool:
        """Check if a snapshot exists at the given path.

        Args:
            path: Storage path to check.

        Returns:
            True if snapshot exists, False otherwise.
        """
        return Path(path).exists()


class S3SnapshotStore:
    """AWS S3 implementation of SnapshotStore.

    Stores snapshots as JSON objects in S3 with optional compression.
    Suitable for production deployments with high availability needs.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str | None = None,
    ) -> None:
        """Initialize S3 snapshot store.

        Args:
            bucket: S3 bucket name.
            prefix: Optional prefix for all snapshot paths.
            region: AWS region (uses default if not specified).
        """
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.region = region
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create S3 client (lazy initialization)."""
        if self._client is None:
            try:
                import boto3

                self._client = boto3.client("s3", region_name=self.region)
            except ImportError as e:
                raise SnapshotStoreError(
                    "boto3 required for S3SnapshotStore. Install with: pip install boto3"
                ) from e
        return self._client

    def _build_key(self, tenant_id: str, snapshot: InvestigationSnapshot) -> str:
        """Build S3 key for a snapshot.

        Args:
            tenant_id: Tenant identifier.
            snapshot: The snapshot to store.

        Returns:
            S3 object key.
        """
        parts = [
            self.prefix,
            tenant_id,
            "snapshots",
            str(snapshot.investigation_id),
            f"{snapshot.checkpoint.value}.snapshot",
        ]
        return "/".join(p for p in parts if p)

    async def store(
        self,
        snapshot: InvestigationSnapshot,
        tenant_id: str,
    ) -> str:
        """Store a snapshot to S3.

        Args:
            snapshot: The investigation snapshot to store.
            tenant_id: Tenant identifier for path namespacing.

        Returns:
            S3 URI where the snapshot was written (s3://bucket/key).
        """
        import json

        client = self._get_client()
        key = self._build_key(tenant_id, snapshot)

        try:
            data = snapshot.model_dump(mode="json")
            body = json.dumps(data, default=str).encode("utf-8")
            client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        except Exception as e:
            raise SnapshotStoreError(f"Failed to store snapshot to S3: {e}") from e

        return f"s3://{self.bucket}/{key}"

    async def retrieve(
        self,
        path: str,
    ) -> InvestigationSnapshot:
        """Retrieve a snapshot from S3.

        Args:
            path: S3 URI (s3://bucket/key) or just the key.

        Returns:
            The deserialized InvestigationSnapshot.
        """
        import json

        from dataing.core.snapshot import InvestigationSnapshot

        client = self._get_client()

        # Parse S3 URI if provided
        if path.startswith("s3://"):
            path = path[5:]  # Remove s3://
            bucket, key = path.split("/", 1)
        else:
            bucket = self.bucket
            key = path

        try:
            response = client.get_object(Bucket=bucket, Key=key)
            body = response["Body"].read().decode("utf-8")
            data = json.loads(body)
            return InvestigationSnapshot.model_validate(data)
        except client.exceptions.NoSuchKey:
            raise SnapshotNotFoundError(f"Snapshot not found: {path}") from None
        except Exception as e:
            raise SnapshotStoreError(f"Failed to retrieve snapshot from S3: {e}") from e

    async def exists(self, path: str) -> bool:
        """Check if a snapshot exists in S3.

        Args:
            path: S3 URI (s3://bucket/key) or just the key.

        Returns:
            True if snapshot exists, False otherwise.
        """
        client = self._get_client()

        # Parse S3 URI if provided
        if path.startswith("s3://"):
            path = path[5:]
            bucket, key = path.split("/", 1)
        else:
            bucket = self.bucket
            key = path

        try:
            client.head_object(Bucket=bucket, Key=key)
            return True
        except Exception:
            return False
