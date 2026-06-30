from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping, Sequence
from typing import Any

HASH_PREFIX = "sha256:"
REDACTED = "[REDACTED]"
DEFAULT_REDACT_FIELDS = frozenset({"api_key", "authorization", "token", "secret"})


def hash_api_key(raw_key: str) -> str:
    """Hash an API key for config storage."""
    if not raw_key:
        raise ValueError("api key must not be empty")

    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return f"{HASH_PREFIX}{digest}"


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Verify a raw API key against a stored SHA-256 digest."""
    if not raw_key or not stored_hash:
        return False

    try:
        candidate = hash_api_key(raw_key)
    except ValueError:
        return False

    return hmac.compare_digest(candidate, stored_hash)


def redact_secrets(value: Any, redact_fields: set[str] | frozenset[str] = DEFAULT_REDACT_FIELDS) -> Any:
    """Return a copy of value with sensitive dict fields redacted."""
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(field in key_text for field in redact_fields):
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_secrets(item, redact_fields)
        return redacted

    if isinstance(value, tuple):
        return tuple(redact_secrets(item, redact_fields) for item in value)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_secrets(item, redact_fields) for item in value]

    return value

