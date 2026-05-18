"""Azure Blob Storage integration for contract file uploads.

Uses the sync BlobServiceClient (fits our FastAPI sync routes). Connection
string is read from env var AZURE_STORAGE_CONNECTION_STRING. Container name
defaults to 'xiaoshou-contracts' and can be overridden via
AZURE_STORAGE_CONTAINER.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CONTAINER = "xiaoshou-contracts"
SAS_TTL_MINUTES = 10


def _conn_string() -> Optional[str]:
    return os.getenv("AZURE_STORAGE_CONNECTION_STRING")


def _container_name() -> str:
    return os.getenv("AZURE_STORAGE_CONTAINER", DEFAULT_CONTAINER)


def _client():
    """Lazy-import the azure SDK so the app still boots when the package
    or the connection string is missing (e.g. local dev, unit tests)."""
    conn = _conn_string()
    if not conn:
        raise RuntimeError(
            "AZURE_STORAGE_CONNECTION_STRING is not set; "
            "contract file upload is unavailable."
        )
    try:
        from azure.storage.blob import BlobServiceClient  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "azure-storage-blob is not installed. Add it to requirements.txt."
        ) from exc
    return BlobServiceClient.from_connection_string(conn)


def ensure_container() -> None:
    """Best-effort: create the private container on first use.
    Called at app startup or lazily before each upload."""
    try:
        svc = _client()
    except RuntimeError as e:
        logger.warning("azure_blob: skip ensure_container (%s)", e)
        return
    container = _container_name()
    try:
        svc.create_container(container)
        logger.info("azure_blob: container %s created", container)
    except Exception as e:  # ResourceExistsError or other — idempotent
        # Container likely already exists, which is the normal case.
        logger.debug("azure_blob: ensure_container no-op (%s)", e)


def upload_bytes(
    data: bytes, *, filename: str, content_type: str, prefix: str = ""
) -> tuple[str, str]:
    """Upload `data` to a new blob. Returns (blob_name, blob_url).

    blob_name is path-like (prefix/uuid-filename).
    blob_url is the full https:// URL (no SAS).
    """
    svc = _client()
    container = _container_name()
    # Build a unique, collision-resistant name while keeping the original
    # filename for content-disposition-ish debugging.
    safe_name = os.path.basename(filename).replace("/", "_")
    blob_name = f"{prefix.strip('/')}/{uuid.uuid4().hex}-{safe_name}" if prefix else \
        f"{uuid.uuid4().hex}-{safe_name}"
    client = svc.get_blob_client(container=container, blob=blob_name)
    from azure.storage.blob import ContentSettings  # type: ignore
    client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )
    return blob_name, client.url


def delete_blob(blob_name_or_url: str) -> None:
    """Delete a blob by name or by the full URL we stored previously."""
    svc = _client()
    container = _container_name()
    blob_name = _name_from_url(blob_name_or_url, container)
    try:
        svc.get_blob_client(container=container, blob=blob_name).delete_blob()
    except Exception as e:
        logger.warning("azure_blob: delete_blob(%s) failed: %s", blob_name, e)


def sas_url(blob_name_or_url: str, *, ttl_minutes: int = SAS_TTL_MINUTES) -> str:
    """Generate a short-lived read-only SAS URL for client download."""
    from azure.storage.blob import (  # type: ignore
        BlobSasPermissions,
        generate_blob_sas,
    )
    svc = _client()
    container = _container_name()
    blob_name = _name_from_url(blob_name_or_url, container)
    sas = generate_blob_sas(
        account_name=svc.account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=svc.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )
    base = svc.get_blob_client(container=container, blob=blob_name).url
    return f"{base}?{sas}"


def _name_from_url(name_or_url: str, container: str) -> str:
    """Accept either the bare blob name or the blob URL we stored."""
    if not name_or_url:
        return name_or_url
    if "://" not in name_or_url:
        return name_or_url
    # Strip protocol/host and leading `container/`
    tail = name_or_url.split("://", 1)[1].split("/", 1)[-1]
    prefix = f"{container}/"
    if tail.startswith(prefix):
        return tail[len(prefix):]
    return tail


def generate_upload_sas(
    blob_name: str,
    content_type: str,
    *,
    ttl_minutes: int = 15,
) -> tuple[str, datetime]:
    """Generate a write-capable SAS URL for direct client upload to Azure Blob.

    Returns (sas_url, expires_at) where expires_at is UTC datetime.
    Raises RuntimeError if not configured.
    """
    from azure.storage.blob import (  # type: ignore
        BlobSasPermissions,
        generate_blob_sas,
    )
    svc = _client()
    container = _container_name()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    sas = generate_blob_sas(
        account_name=svc.account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=svc.credential.account_key,
        permission=BlobSasPermissions(write=True, create=True),
        expiry=expires_at,
        content_type=content_type,
    )
    base = svc.get_blob_client(container=container, blob=blob_name).url
    return f"{base}?{sas}", expires_at


def head_blob(blob_name: str) -> bool:
    """Return True if the blob exists, False otherwise."""
    svc = _client()
    container = _container_name()
    try:
        svc.get_blob_client(container=container, blob=blob_name).get_blob_properties()
        return True
    except Exception:
        return False


def blob_url(blob_name: str) -> str:
    """Return the canonical (no SAS) URL for a blob name."""
    svc = _client()
    container = _container_name()
    return svc.get_blob_client(container=container, blob=blob_name).url


def is_configured() -> bool:
    return bool(_conn_string())
