#!/usr/bin/env python3
"""Helpers for rotating LlamaCloud API tokens with persistent state."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

import httpx

try:
    from llama_cloud import AsyncLlamaCloud
except ImportError:  # pragma: no cover - callers already gate on install
    AsyncLlamaCloud = None


T = TypeVar("T")

TOKEN_ENV_PATTERN = re.compile(r"^LLAMA_CLOUD_API_KEY(?:_?(\d+))?$")
TOKEN_HINT_PATTERN = re.compile(
    r"^LLAMA_CLOUD_API_KEY(?:_?(\d+))?(?:_DISABLED_UNTIL|_BLOCKED_UNTIL|_NOT_BEFORE)?$"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = PROJECT_ROOT / ".cache" / "llamacloud_token_state.json"
DOTENV_PATH = PROJECT_ROOT / ".env"
MANUAL_DISABLE_SUFFIXES = ("_DISABLED_UNTIL", "_BLOCKED_UNTIL", "_NOT_BEFORE")
MONTH_LOOKUP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass(frozen=True)
class TokenInfo:
    env_name: str
    index: int
    value: str
    fingerprint: str
    masked_value: str

    @property
    def label(self) -> str:
        return f"{self.env_name} ({self.masked_value})"


@dataclass
class TokenFailure:
    category: str
    message: str
    cooldown_until: datetime | None = None
    permanent: bool = False
    should_retry_other_tokens: bool = True


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return _as_utc(dt).isoformat()


def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return _as_utc(datetime.fromisoformat(dt_str.replace("Z", "+00:00")))
    except ValueError:
        return None


def _mask_token(token: str) -> str:
    if len(token) <= 8:
        return token[:2] + "..."
    return f"{token[:6]}...{token[-4:]}"


def _fingerprint_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _parse_dotenv_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""

    try:
        parsed = shlex.split(value, comments=True, posix=True)
    except ValueError:
        parsed = None

    if parsed is not None:
        if not parsed:
            return ""
        if len(parsed) == 1:
            return parsed[0]
        return " ".join(parsed)

    if "#" in value:
        value = value.split("#", 1)[0].rstrip()
    return value.strip().strip("'").strip('"')


def _read_dotenv_values() -> dict[str, str]:
    if not DOTENV_PATH.exists():
        return {}

    values: dict[str, str] = {}
    line_pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")

    try:
        lines = DOTENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = line_pattern.match(raw_line)
        if not match:
            continue

        key, raw_value = match.groups()
        if not TOKEN_HINT_PATTERN.match(key):
            continue

        values[key] = _parse_dotenv_value(raw_value)

    return values


def _get_config_value(name: str) -> str | None:
    env_value = os.getenv(name)
    if env_value is not None and env_value.strip():
        return env_value.strip()

    dotenv_value = _read_dotenv_values().get(name)
    if dotenv_value is not None and dotenv_value.strip():
        return dotenv_value.strip()

    return None


def load_llamacloud_tokens() -> list[TokenInfo]:
    """Return unique configured LlamaCloud tokens in deterministic order."""
    discovered: list[tuple[int, str, str]] = []
    seen_values: set[str] = set()
    dotenv_values = _read_dotenv_values()
    candidate_names = set(os.environ) | set(dotenv_values)

    for env_name in candidate_names:
        match = TOKEN_ENV_PATTERN.match(env_name)
        if not match:
            continue
        token = _get_config_value(env_name)
        if not token:
            continue
        cleaned = token.strip()
        if not cleaned or cleaned in seen_values:
            continue
        index = int(match.group(1) or "1")
        discovered.append((index, env_name, cleaned))
        seen_values.add(cleaned)

    discovered.sort(key=lambda item: (item[0], item[1]))
    return [
        TokenInfo(
            env_name=env_name,
            index=index,
            value=token,
            fingerprint=_fingerprint_token(token),
            masked_value=_mask_token(token),
        )
        for index, env_name, token in discovered
    ]


def has_llamacloud_tokens() -> bool:
    return bool(load_llamacloud_tokens())


def token_count() -> int:
    return len(load_llamacloud_tokens())


def _parse_datetime_hint(value: str | None, now: datetime | None = None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    return _extract_retry_after(value, _as_utc(now or _utc_now()))


def _manual_disable_until(token: TokenInfo, now: datetime | None = None) -> datetime | None:
    now = _as_utc(now or _utc_now())
    for suffix in MANUAL_DISABLE_SUFFIXES:
        candidate = _parse_datetime_hint(_get_config_value(f"{token.env_name}{suffix}"), now=now)
        if candidate is not None:
            return candidate
    return None


class TokenStateStore:
    """Persist non-secret token health metadata between runs."""

    def __init__(self, state_path: Path | None = None):
        self.state_path = state_path or STATE_FILE
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"version": 1, "updated_at": None, "tokens": {}}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "updated_at": None, "tokens": {}}

    def save(self) -> None:
        self._state["updated_at"] = _to_iso(_utc_now())
        tmp_path = self.state_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._state, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self.state_path)

    def entry_for(self, token: TokenInfo) -> dict[str, Any]:
        tokens = self._state.setdefault("tokens", {})
        entry = tokens.setdefault(token.fingerprint, {})
        entry.setdefault("env_name", token.env_name)
        entry.setdefault("masked_value", token.masked_value)
        entry.setdefault("token_index", token.index)
        return entry

    def is_usable(self, token: TokenInfo, now: datetime | None = None) -> tuple[bool, str | None]:
        now = _as_utc(now or _utc_now())
        entry = self.entry_for(token)

        manual_disable_until = _manual_disable_until(token, now=now)
        if manual_disable_until and manual_disable_until > now:
            return False, f"manually disabled until {manual_disable_until.isoformat()}"

        if entry.get("permanent_disable"):
            return False, "permanently disabled"

        cooldown_until = _parse_iso(entry.get("cooldown_until"))
        if cooldown_until and cooldown_until > now:
            return False, f"cooldown until {cooldown_until.isoformat()}"

        return True, None

    def score(self, token: TokenInfo) -> tuple[datetime, int, str]:
        entry = self.entry_for(token)
        last_attempt = _parse_iso(entry.get("last_attempt_at")) or datetime(1970, 1, 1, tzinfo=timezone.utc)
        failure_count = int(entry.get("failure_count") or 0)
        return last_attempt, failure_count, token.env_name

    def mark_attempt(self, token: TokenInfo, started_at: datetime | None = None) -> None:
        entry = self.entry_for(token)
        entry["last_attempt_at"] = _to_iso(started_at or _utc_now())
        self.save()

    def mark_success(self, token: TokenInfo, succeeded_at: datetime | None = None) -> None:
        when = _as_utc(succeeded_at or _utc_now())
        entry = self.entry_for(token)
        entry["last_attempt_at"] = _to_iso(when)
        entry["last_success_at"] = _to_iso(when)
        entry["last_error"] = None
        entry["last_error_category"] = None
        entry["last_error_at"] = None
        entry["cooldown_until"] = None
        entry["permanent_disable"] = False
        entry["failure_count"] = 0
        entry["success_count"] = int(entry.get("success_count") or 0) + 1
        self.save()

    def mark_failure(self, token: TokenInfo, failure: TokenFailure, failed_at: datetime | None = None) -> None:
        when = _as_utc(failed_at or _utc_now())
        entry = self.entry_for(token)
        entry["last_attempt_at"] = _to_iso(when)
        entry["last_error_at"] = _to_iso(when)
        entry["last_error"] = failure.message[:1000]
        entry["last_error_category"] = failure.category
        entry["permanent_disable"] = bool(failure.permanent)
        entry["cooldown_until"] = _to_iso(failure.cooldown_until)
        entry["failure_count"] = int(entry.get("failure_count") or 0) + 1
        self.save()

    def next_retry_after(self, tokens: list[TokenInfo]) -> datetime | None:
        retry_points: list[datetime] = []
        for token in tokens:
            entry = self.entry_for(token)
            retry_at = _parse_iso(entry.get("cooldown_until"))
            if retry_at is not None:
                retry_points.append(retry_at)
        return min(retry_points) if retry_points else None


def _extract_status_code(exc: BaseException) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_code = getattr(response, "status_code", None)
    if isinstance(response_code, int):
        return response_code
    return None


def _extract_retry_after(message: str, now: datetime) -> datetime | None:
    lowered = message.lower()

    for pattern in (
        r"(20\d{2}-\d{2}-\d{2}[t ][0-9:\-+.zZ]+)",
        r"(20\d{2}-\d{2}-\d{2})",
    ):
        match = re.search(pattern, message)
        if not match:
            continue
        value = match.group(1).replace("Z", "+00:00")
        if len(value) == 10:
            try:
                return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            return _as_utc(datetime.fromisoformat(value))
        except ValueError:
            continue

    rel_match = re.search(r"(?:retry after|available in|try again in)\s+(\d+)\s+(minute|minutes|hour|hours|day|days)", lowered)
    if rel_match:
        amount = int(rel_match.group(1))
        unit = rel_match.group(2)
        if unit.startswith("minute"):
            return now + timedelta(minutes=amount)
        if unit.startswith("hour"):
            return now + timedelta(hours=amount)
        return now + timedelta(days=amount)

    text_patterns = (
        r"\b([A-Za-z]+)\s+(\d{1,2})(?:,\s*(20\d{2}))?\b",
        r"\b(\d{1,2})\s+([A-Za-z]+)(?:\s+(20\d{2}))?\b",
    )
    for pattern in text_patterns:
        match = re.search(pattern, message)
        if not match:
            continue
        groups = match.groups()
        if groups[0].isalpha():
            month_name, day_text, year_text = groups
        else:
            day_text, month_name, year_text = groups
        month = MONTH_LOOKUP.get(month_name.lower())
        if not month:
            continue
        year = int(year_text) if year_text else now.year
        try:
            candidate = datetime(year, month, int(day_text), tzinfo=timezone.utc)
        except ValueError:
            continue
        if candidate + timedelta(days=1) < now and not year_text:
            candidate = candidate.replace(year=year + 1)
        return candidate

    return None


def classify_token_failure(exc: BaseException, now: datetime | None = None) -> TokenFailure:
    now = _as_utc(now or _utc_now())
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    status_code = _extract_status_code(exc)
    retry_after = _extract_retry_after(message, now)

    if isinstance(exc, (FileNotFoundError, IsADirectoryError, PermissionError)):
        return TokenFailure(
            category="local_file",
            message=message,
            should_retry_other_tokens=False,
        )

    if status_code in {401, 403} or any(
        term in lowered for term in ("invalid api key", "unauthorized", "forbidden", "authentication", "auth failed")
    ):
        return TokenFailure(
            category="auth",
            message=message,
            permanent=True,
        )

    if status_code == 429 or any(
        term in lowered
        for term in (
            "rate limit",
            "quota",
            "credit",
            "credits",
            "page limit",
            "usage limit",
            "limit reached",
            "exceeded",
            "until ",
        )
    ):
        return TokenFailure(
            category="quota",
            message=message,
            cooldown_until=retry_after or (now + timedelta(hours=12)),
        )

    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)) or any(
        term in lowered for term in ("timed out", "timeout", "connection reset", "temporary failure", "dns")
    ):
        return TokenFailure(
            category="network",
            message=message,
            cooldown_until=now + timedelta(minutes=5),
        )

    if status_code and status_code >= 500 or any(
        term in lowered for term in ("internal server error", "bad gateway", "service unavailable", "server error")
    ):
        return TokenFailure(
            category="server",
            message=message,
            cooldown_until=now + timedelta(minutes=15),
        )

    if status_code and status_code >= 400:
        return TokenFailure(
            category="client_error",
            message=message,
            cooldown_until=retry_after or (now + timedelta(hours=1)),
        )

    return TokenFailure(
        category="unknown",
        message=message,
        cooldown_until=retry_after or (now + timedelta(minutes=30)),
    )


def _summarize_attempts(attempts: list[tuple[TokenInfo, TokenFailure]]) -> str:
    parts = []
    for token, failure in attempts:
        label = token.label
        if failure.permanent:
            parts.append(f"{label}: {failure.category}")
            continue
        if failure.cooldown_until:
            parts.append(f"{label}: {failure.category} until {failure.cooldown_until.isoformat()}")
        else:
            parts.append(f"{label}: {failure.category}")
    return "; ".join(parts)


async def run_with_rotating_tokens(
    operation: Callable[[AsyncLlamaCloud, TokenInfo], Awaitable[T]],
    *,
    logger: Callable[[str], None] = print,
    state_path: Path | None = None,
) -> tuple[T, TokenInfo]:
    """Run a LlamaCloud operation using the best available token."""
    if AsyncLlamaCloud is None:
        raise RuntimeError("llama-cloud is not installed")

    tokens = load_llamacloud_tokens()
    if not tokens:
        raise RuntimeError(
            "No LlamaCloud API tokens found. Set LLAMA_CLOUD_API_KEY or LLAMA_CLOUD_API_KEY2/3 in .env."
        )

    now = _utc_now()
    store = TokenStateStore(state_path=state_path)
    usable: list[TokenInfo] = []
    skipped: list[str] = []
    for token in tokens:
        is_usable, reason = store.is_usable(token, now=now)
        if is_usable:
            usable.append(token)
        else:
            skipped.append(f"{token.label}: {reason}")

    if not usable:
        next_retry = store.next_retry_after(tokens)
        detail = f" Next retry after {next_retry.isoformat()}." if next_retry else ""
        raise RuntimeError(
            "No usable LlamaCloud API tokens are currently available." + detail
        )

    usable.sort(key=store.score)

    if skipped:
        logger("   ⏭️  Skipping unavailable tokens:")
        for item in skipped:
            logger(f"      - {item}")

    attempts: list[tuple[TokenInfo, TokenFailure]] = []
    last_error: BaseException | None = None

    for index, token in enumerate(usable, 1):
        started_at = _utc_now()
        logger(f"   🔑 Trying token {token.label} ({index}/{len(usable)})...")
        store.mark_attempt(token, started_at=started_at)
        client = AsyncLlamaCloud(api_key=token.value)
        try:
            result = await operation(client, token)
            store.mark_success(token)
            return result, token
        except Exception as exc:  # pragma: no cover - exercised via callers
            failure = classify_token_failure(exc, now=_utc_now())
            if not failure.should_retry_other_tokens:
                store.mark_failure(token, failure)
                raise
            store.mark_failure(token, failure)
            last_error = exc
            attempts.append((token, failure))
            logger(f"   ⚠️  {token.label} failed with {failure.category}: {failure.message}")
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                await close()

    summary = _summarize_attempts(attempts)
    raise RuntimeError(f"All configured LlamaCloud tokens failed. {summary}") from last_error
