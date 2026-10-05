"""The run's Jev client: one budget for the whole run, and a replay miss never crashes it.

Header and enum questions (choice) read engine/tests/cassettes/mapping, triage and PII
questions (noul and score) read engine/tests/cassettes/run. In replay a question with no
recording is answered Unresolved("not_recorded"), so it goes to the human queue, and is kept
with its request so the run can count it and `intake jev record-run` knows what to record.
"""

import math
from decimal import Decimal
from pathlib import Path
from typing import Any

from intake.config import JEV_CHARS_PER_TOKEN
from jev_client import (
    CassetteMiss,
    JevClient,
    JevRequest,
    JevResponse,
    Unresolved,
    canonical_json,
    estimate_cost_usd,
    request_hash,
)
from jev_client.client import DEFAULT_CASSETTE_DIR

MAPPING_CASSETTES = DEFAULT_CASSETTE_DIR / "mapping"
RUN_CASSETTES = DEFAULT_CASSETTE_DIR / "run"


def cassette_dir_for(request: JevRequest) -> Path:
    """Choice questions are mapping questions (PR 7); noul and score are triage and PII."""
    kinds = {q.type for q in request.questions.values()}
    return MAPPING_CASSETTES if kinds == {"choice"} else RUN_CASSETTES


class RunJevClient(JevClient):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.misses: dict[str, JevRequest] = {}

    def ask(self, request: JevRequest, *, pii_cleared: bool = False) -> JevResponse | Unresolved:
        self._cassette_dir = cassette_dir_for(request)
        try:
            return super().ask(request, pii_cleared=pii_cleared)
        except CassetteMiss:
            self.misses[request_hash(request.body())] = request
            return Unresolved(reason="not_recorded", question_ids=tuple(request.questions))


def estimate_tokens(requests: dict[str, JevRequest]) -> int:
    return sum(
        math.ceil(len(canonical_json(r.body()).encode()) / JEV_CHARS_PER_TOKEN)
        for r in requests.values()
    )


def estimate_cost(requests: dict[str, JevRequest]) -> Decimal:
    return estimate_cost_usd(estimate_tokens(requests))
