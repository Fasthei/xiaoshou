"""Azure OpenAI client factory.

The env var AZURE_OPENAI_ENDPOINT may include a path/query
(e.g. .../openai/responses?api-version=...). The AzureOpenAI SDK
expects the plain host origin, so we normalise it here.
"""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from app.config import get_settings


def _host_only(endpoint: str) -> str:
    if not endpoint:
        return ""
    p = urlparse(endpoint)
    if not p.scheme:
        # bare host
        return f"https://{endpoint}".rstrip("/")
    return f"{p.scheme}://{p.netloc}".rstrip("/")


@lru_cache(maxsize=1)
def get_azure_openai_client():
    """Return a cached AzureOpenAI client.

    Raises RuntimeError if not configured — callers should surface a 400.
    Import is lazy so the `openai` package is only required at runtime,
    not at test collection time.
    """
    s = get_settings()
    if not s.AZURE_OPENAI_API_KEY or not s.AZURE_OPENAI_ENDPOINT:
        raise RuntimeError("AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT not configured")

    from openai import AzureOpenAI  # type: ignore

    return AzureOpenAI(
        api_key=s.AZURE_OPENAI_API_KEY,
        api_version=s.AZURE_OPENAI_API_VERSION,
        azure_endpoint=_host_only(s.AZURE_OPENAI_ENDPOINT),
    )


def deployment_name() -> str:
    return get_settings().AZURE_OPENAI_DEPLOYMENT or "gpt-5.4"
