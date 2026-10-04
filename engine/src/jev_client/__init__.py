"""Typed Jev (TypeSafe) client with live, replay, record, and off modes."""

from jev_client.cassettes import CassetteMiss, canonical_json, request_hash
from jev_client.client import JevClient, JevHTTPError, SpendNotApproved
from jev_client.cost import RunUsage, estimate_cost_usd
from jev_client.types import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    JevRequest,
    JevResponse,
    NoulAnswer,
    NoulCriteria,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    Unresolved,
    minimize_state,
)

__version__ = "0.0.0"

__all__ = [
    "Answer",
    "CassetteMiss",
    "ChoiceAnswer",
    "ChoiceQuestion",
    "JevClient",
    "JevHTTPError",
    "JevRequest",
    "JevResponse",
    "NoulAnswer",
    "NoulCriteria",
    "NoulQuestion",
    "RunUsage",
    "ScoreAnswer",
    "ScoreQuestion",
    "SpendNotApproved",
    "Unresolved",
    "canonical_json",
    "estimate_cost_usd",
    "minimize_state",
    "request_hash",
]
