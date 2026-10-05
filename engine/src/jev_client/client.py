"""The Jev client: four modes, retries, the spend guard, and the notes check.

Modes: replay (default) reads cassettes, off answers nothing, live always calls the API and
never reads or writes cassettes, record calls the API for requests with no cassette yet and
saves the answer. live and record spend
money, so the client refuses them unless allow_spend=True is passed on purpose.
"""

import logging
import os
import random
import re
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr

from agency_schema.outputs import JevMode
from intake.config import (
    JEV_API_URL,
    JEV_BACKOFF_BASE_S,
    JEV_BUDGET_USD,
    JEV_MAX_TRIES,
    JEV_TIMEOUT_S,
)
from jev_client.cassettes import CassetteMiss, load_cassette, request_hash, save_cassette
from jev_client.cost import RunUsage, estimate_cost_usd
from jev_client.types import JevRequest, JevResponse, Unresolved, has_notes

log = logging.getLogger("jev_client")

DEFAULT_CASSETTE_DIR = Path(__file__).resolve().parents[2] / "tests" / "cassettes"
RETRY_STATUSES = frozenset({429, 529})


class SpendNotApproved(RuntimeError):
    """live or record was asked for without allow_spend=True."""


class JevHTTPError(RuntimeError):
    """The API refused the request. The text holds a short, redacted excerpt of the body."""

    def __init__(self, status_code: int, excerpt: str) -> None:
        self.status_code = status_code
        super().__init__(f"Jev returned HTTP {status_code}: {excerpt}")


class JevBadReply(ValueError):
    """The API answered (and billed) but the reply does not fit the questions asked."""


ERROR_EXCERPT_CHARS = 200
_BEARER = re.compile(r"bearer\s*\S*", re.IGNORECASE)
_KEY_PREFIX_CHARS = 8


def redact_error_body(text: str, key: str) -> str:
    """Remove the key, any bearer token, and long echoes from an error body before showing it.

    The key is removed whole and by its first 8 characters, since some servers quote a prefix.
    """
    if key:
        text = text.replace(key, "[redacted]")
        if len(key) >= _KEY_PREFIX_CHARS:
            text = re.sub(re.escape(key[:_KEY_PREFIX_CHARS]) + r"\S*", "[redacted]", text)
    text = _BEARER.sub("[redacted]", text)
    if len(text) > ERROR_EXCERPT_CHARS:
        text = text[:ERROR_EXCERPT_CHARS] + " [cut]"
    return text


def _token_count(usage: Any, field: str) -> int:
    value = usage.get(field) if isinstance(usage, dict) else None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


class JevClient:
    def __init__(
        self,
        *,
        mode: JevMode,
        api_key: str | None,
        cassette_dir: Path = DEFAULT_CASSETTE_DIR,
        allow_spend: bool = False,
        budget_usd: Decimal = JEV_BUDGET_USD,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        spends = mode in (JevMode.LIVE, JevMode.RECORD)
        if spends and not allow_spend:
            raise SpendNotApproved(
                f"Jev mode {mode} spends money. Pass allow_spend=True only after Alex approves."
            )
        if spends and not api_key:
            raise ValueError("TYPESAFE_API_KEY is not set")
        self.mode = mode
        self._key = SecretStr(api_key or "")
        self._cassette_dir = cassette_dir
        self._budget = budget_usd
        self._transport = transport
        self._sleep = sleep
        self._rand = rand
        self._calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._tripped = False

    @classmethod
    def from_env(cls, *, allow_spend: bool = False, **kwargs: Any) -> "JevClient":
        mode = JevMode(os.environ.get("JEV_MODE", JevMode.REPLAY.value))
        key = os.environ.get("TYPESAFE_API_KEY")
        return cls(mode=mode, api_key=key, allow_spend=allow_spend, **kwargs)

    def __repr__(self) -> str:
        return f"JevClient(mode={self.mode.value}, budget_tripped={self._tripped})"

    @property
    def usage(self) -> RunUsage:
        return RunUsage(
            mode=self.mode,
            calls=self._calls,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            estimated_cost_usd=estimate_cost_usd(self._input_tokens),
            budget_usd=self._budget,
            budget_tripped=self._tripped,
        )

    def ask(self, request: JevRequest, *, pii_cleared: bool = False) -> JevResponse | Unresolved:
        if not pii_cleared and has_notes(request.state):
            raise ValueError("A notes field cannot go to Jev before it passes the PII gate")
        qids = tuple(request.questions)
        if self.mode == JevMode.OFF:
            return Unresolved(reason="mode_off", question_ids=qids)
        if self._tripped:
            return Unresolved(reason="budget_tripped", question_ids=qids)
        body = request.body()
        # live always calls the API. Only replay and record read cassettes.
        raw = None if self.mode == JevMode.LIVE else load_cassette(self._cassette_dir, body)
        saved_at: Path | None = None
        if raw is None:
            if self.mode == JevMode.REPLAY:
                raise CassetteMiss(request_hash(body), self._cassette_dir)
            raw = self._post(body)
            if self.mode == JevMode.RECORD:
                # Saved before validation: the reply was paid for, so a retry must not pay again.
                saved_at = save_cassette(self._cassette_dir, body, raw)
        # Counted before validation too: a reply that fails the checks below was still billed.
        self._count(raw.get("usage"))
        try:
            response = JevResponse.model_validate(raw)
            response.check_matches(request)
        except ValueError as error:
            where = ""
            if saved_at:
                where = f" The paid reply was saved at {saved_at}; delete it to re-record."
            raise JevBadReply(f"Jev reply rejected: {error}.{where}") from error
        return response

    def _count(self, usage: Any) -> None:
        self._calls += 1
        in_tokens = _token_count(usage, "input_tokens")
        if in_tokens == 0:
            log.warning("Jev reply has no usable input token count; it is counted as 0 tokens")
        self._input_tokens += in_tokens
        self._output_tokens += _token_count(usage, "output_tokens")
        cost = estimate_cost_usd(self._input_tokens)
        if cost >= self._budget:
            self._tripped = True
            log.warning(
                "Jev budget reached: estimated $%s of $%s. Jev is off for the rest of this "
                "run and remaining questions go to the human queue.",
                cost,
                self._budget,
            )

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._key.get_secret_value()}"}
        with httpx.Client(transport=self._transport, timeout=JEV_TIMEOUT_S) as http:
            for attempt in range(1, JEV_MAX_TRIES + 1):
                reply = http.post(JEV_API_URL, json=body, headers=headers)
                if reply.status_code == 200:
                    try:
                        data = reply.json()
                    except ValueError:
                        data = None
                    if not isinstance(data, dict):
                        self._count(None)
                        raise JevBadReply("Jev reply rejected: the body is not a JSON object.")
                    return data
                if reply.status_code not in RETRY_STATUSES or attempt == JEV_MAX_TRIES:
                    excerpt = redact_error_body(reply.text, self._key.get_secret_value())
                    raise JevHTTPError(reply.status_code, excerpt)
                window = JEV_BACKOFF_BASE_S * 2 ** (attempt - 1)
                delay = window / 2 + self._rand() * window / 2
                log.info("Jev HTTP %s, try %s, waiting %.2fs", reply.status_code, attempt, delay)
                self._sleep(delay)
        raise AssertionError("unreachable")
