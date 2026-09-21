"""Short-lived, single-use capability tokens for phone mutations."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PendingConfirmation:
    action: str
    fingerprint: str
    expires_at: float


class ConfirmationGate:
    def __init__(self, *, ttl_seconds: float = 300.0, max_pending: int = 256) -> None:
        self._ttl_seconds = max(1.0, float(ttl_seconds))
        self._max_pending = max(1, int(max_pending))
        self._pending: dict[str, PendingConfirmation] = {}

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def clear(self) -> None:
        self._pending.clear()

    def _discard_expired(self) -> None:
        now = time.monotonic()
        self._pending = {
            token: item for token, item in self._pending.items() if item.expires_at >= now
        }

    def issue(self, action: str, payload: dict[str, Any]) -> str:
        self._discard_expired()
        while len(self._pending) >= self._max_pending:
            oldest = min(self._pending, key=lambda token: self._pending[token].expires_at)
            self._pending.pop(oldest, None)
        token = secrets.token_urlsafe(24)
        self._pending[token] = PendingConfirmation(
            action=action,
            fingerprint=self._fingerprint(payload),
            expires_at=time.monotonic() + self._ttl_seconds,
        )
        return token

    def consume(self, token: str, action: str, payload: dict[str, Any]) -> bool:
        self._discard_expired()
        item = self._pending.pop(str(token or ""), None)
        return bool(
            item
            and item.action == action
            and item.fingerprint == self._fingerprint(payload)
            and item.expires_at >= time.monotonic()
        )
