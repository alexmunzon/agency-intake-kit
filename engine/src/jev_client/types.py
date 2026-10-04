"""Request and answer types for TypeSafe's System One endpoint (docs/jev.md has the source)."""

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, JsonValue, StrictInt

from agency_schema.exceptions import Probability
from agency_schema.lineage import NonEmpty, StrictModel
from intake.config import JEV_MODEL


class NoulCriteria(StrictModel):
    true: JsonValue
    false: JsonValue


class NoulQuestion(StrictModel):
    """A yes or no question. The answer is a probability that the answer is yes."""

    type: Literal["noul"]
    instructions: JsonValue
    criteria: NoulCriteria | None


class ChoiceQuestion(StrictModel):
    """Pick one option. Criteria map each option key to a description, or None."""

    type: Literal["choice"]
    instructions: JsonValue
    criteria: dict[NonEmpty, JsonValue] = Field(min_length=1, max_length=255)


class ScoreQuestion(StrictModel):
    """Place the input on an ordered scale of 2 to 10 described levels, lowest first."""

    type: Literal["score"]
    instructions: JsonValue
    criteria: list[JsonValue] = Field(min_length=2, max_length=10)


Question = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]


class JevRequest(StrictModel):
    state: JsonValue
    questions: dict[NonEmpty, Question] = Field(min_length=1)

    def body(self) -> dict[str, Any]:
        """The exact JSON body sent to the API. Cassettes are keyed by its hash."""
        questions: dict[str, Any] = {}
        for qid, question in self.questions.items():
            q = question.model_dump(mode="json")
            if q["criteria"] is None:
                del q["criteria"]
            questions[qid] = q
        return {"state": self.state, "model": JEV_MODEL, "questions": questions}


class _Answer(StrictModel):
    # The API may add fields later; ignoring them keeps old cassettes and live calls working.
    model_config = ConfigDict(extra="ignore", frozen=True)


class NoulAnswer(_Answer):
    type: Literal["noul"]
    noul: Probability


class ChoiceAnswer(_Answer):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, Probability]
    confidence: Probability


class ScoreAnswer(_Answer):
    type: Literal["score"]
    score: float  # weighted mean of the level numbers, so 1.43 is between levels 1 and 2
    legend: dict[str, JsonValue]  # level number as text, "0" first, to the level's description
    probabilities: dict[str, Probability]
    confidence: Probability


Answer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class TokenUsage(_Answer):
    input_tokens: Annotated[StrictInt, Field(ge=0)] | None
    output_tokens: Annotated[StrictInt, Field(ge=0)] | None


class JevResponse(_Answer):
    model: str
    answers: dict[str, Answer]
    usage: TokenUsage

    def check_matches(self, request: JevRequest) -> None:
        """Refuse answers that do not line up one to one with the questions asked.

        A choice answer must pick an offered option, and its probabilities may only name
        offered options. A score must sit between level 0 and the top level, and its
        probabilities may only name level numbers ("0", "1", ...) that were offered.
        """
        if set(self.answers) != set(request.questions):
            raise ValueError("Jev answers do not match the questions asked")
        for qid, answer in self.answers.items():
            question = request.questions[qid]
            if answer.type != question.type:
                raise ValueError(f"Jev answers question {qid} with the wrong type")
            if isinstance(answer, ChoiceAnswer) and isinstance(question, ChoiceQuestion):
                offered = set(question.criteria)
                if answer.choice not in offered or not set(answer.probabilities) <= offered:
                    raise ValueError(f"Jev answers question {qid} with an option not offered")
            if isinstance(answer, ScoreAnswer) and isinstance(question, ScoreQuestion):
                levels = {str(n) for n in range(len(question.criteria))}
                top = len(question.criteria) - 1
                if not set(answer.probabilities) <= levels or not 0 <= answer.score <= top:
                    raise ValueError(f"Jev answers question {qid} with a level not offered")


class Unresolved(StrictModel):
    """No machine answer. Every question in the request goes to the human queue."""

    reason: Literal["mode_off", "budget_tripped"]
    question_ids: tuple[NonEmpty, ...]


def _strip_notes(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {k: _strip_notes(v) for k, v in value.items() if not is_notes_key(k)}
    if isinstance(value, list):
        return [_strip_notes(v) for v in value]
    return value


def is_notes_key(key: str) -> bool:
    return key.strip().casefold() == "notes"


def has_notes(value: JsonValue) -> bool:
    if isinstance(value, Mapping):
        return any(is_notes_key(k) or has_notes(v) for k, v in value.items())
    if isinstance(value, list):
        return any(has_notes(v) for v in value)
    return False


def minimize_state(
    record: Mapping[str, JsonValue], allowlist: set[str], *, pii_cleared: bool = False
) -> dict[str, JsonValue]:
    """Build a Jev `state` from allowlisted fields only.

    A field named notes, at any depth and in any case, is dropped unless the text has
    passed the PII gate (pii_cleared=True), even when the allowlist names it.
    """
    kept = {k: v for k, v in record.items() if k in allowlist}
    if pii_cleared:
        return kept
    stripped = _strip_notes(kept)
    assert isinstance(stripped, dict)
    return stripped
