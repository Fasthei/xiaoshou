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
from urllib.parse import quote, unquote, urlparse

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


def sas_url(
    blob_name_or_url: str,
    *,
    ttl_minutes: int = SAS_TTL_MINUTES,
    download_filename: Optional[str] = None,
) -> str:
    """Generate a short-lived read-only SAS URL for client download.

    若传 ``download_filename`` (例如 "合同.pdf"), 会在 SAS 上额外签入
    ``Content-Disposition: attachment; filename="..."``, 让 Azure Blob 在
    GET 时回 Content-Disposition 强制浏览器下载而不是在新标签页内嵌渲染
    (修复前端 PDF/图片附件点 下载 后只是在新窗口预览不下载的问题).
    """
    from azure.storage.blob import (  # type: ignore
        BlobSasPermissions,
        generate_blob_sas,
    )
    svc = _client()
    container = _container_name()
    blob_name = _name_from_url(blob_name_or_url, container)
    kwargs: dict = dict(
        account_name=svc.account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=svc.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )
    if download_filename:
        # HTTP header 默认按 Latin-1 解码, 直接塞中文文件名会乱码 (例如下载下来变
        # "C骵EO_docx")。走 RFC 5987:
        #   Content-Disposition: attachment; filename="<ascii-fallback>"; filename*=UTF-8''<pct>
        # 现代浏览器 (Chrome/FF/Edge/Safari) 优先认 filename*= 那段, 老浏览器回退
        # 到 ASCII filename。
        raw = (
            download_filename.replace("\\", "_")
            .replace('"', "_")
            .replace("\r", "")
            .replace("\n", "")
        )
        # ASCII fallback: 把非 ASCII 字符替换成 "_", 避免破坏 header 语法
        ascii_fallback = "".join(c if ord(c) < 128 else "_" for c in raw) or "download"
        pct = quote(raw, safe="")  # 全部百分号编码 UTF-8 字节
        kwargs["content_disposition"] = (
            f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{pct}'
        )
    sas = generate_blob_sas(**kwargs)
    base = svc.get_blob_client(container=container, blob=blob_name).url
    return f"{base}?{sas}"


def _name_from_url(name_or_url: str, container: str) -> str:
    """Accept either the bare blob name or the blob URL we stored.

    存进 DB 的 ``file_url`` 是 ``client.url`` (Azure SDK 已经把 blob name 做了
    URL 编码, 比如中文文件名 "合同.pdf" 会变成 "%E5%90%88%E5%90%8C.pdf").
    这里必须把它 unquote 回原始 blob name, 否则下游 ``get_blob_client(blob=...)``
    会对 `%` 再编码一次 (→ `%25E5%2590...`), 导致 BlobNotFound。

    顺手把 query string / fragment 剥掉, 容忍 ``file_url`` 里残留 SAS 的情况。
    """
    if not name_or_url:
        return name_or_url
    if "://" not in name_or_url:
        # 已经是裸 blob name (有可能是新代码或老脚本写进去的)
        return name_or_url
    parsed = urlparse(name_or_url)
    # path 形如 "/<container>/contract/123/uuid-%E5%90%88%E5%90%8C.pdf"
    path = parsed.path.lstrip("/")
    prefix = f"{container}/"
    if path.startswith(prefix):
        path = path[len(prefix):]
    return unquote(path)


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
