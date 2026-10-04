"""The Jev client: four modes, retries, the spend guard, and the notes check.

Modes: replay (default) reads cassettes, off answers nothing, live calls the API, record
calls the API for requests with no cassette yet and saves the answer. live and record spend
money, so the client refuses them unless allow_spend=True is passed on purpose.
"""

import logging
import os
import random
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
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        super().__init__(f"Jev returned HTTP {status_code}: {body[:500]}")


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
        raw = load_cassette(self._cassette_dir, body)
        if raw is None:
            if self.mode == JevMode.REPLAY:
                raise CassetteMiss(request_hash(body), self._cassette_dir)
            raw = self._post(body)
        response = JevResponse.model_validate(raw)
        response.check_matches(request)
        if self.mode == JevMode.RECORD:
            save_cassette(self._cassette_dir, body, raw)
        self._count(response)
        return response

    def _count(self, response: JevResponse) -> None:
        self._calls += 1
        self._input_tokens += response.usage.input_tokens or 0
        self._output_tokens += response.usage.output_tokens or 0
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
                    data: dict[str, Any] = reply.json()
                    return data
                if reply.status_code not in RETRY_STATUSES or attempt == JEV_MAX_TRIES:
                    raise JevHTTPError(reply.status_code, reply.text)
                window = JEV_BACKOFF_BASE_S * 2 ** (attempt - 1)
                delay = window / 2 + self._rand() * window / 2
                log.info("Jev HTTP %s, try %s, waiting %.2fs", reply.status_code, attempt, delay)
                self._sleep(delay)
        raise AssertionError("unreachable")
