"""Header mapping benchmark (PR 17): synonyms alone, synonyms then Jev, synonyms then Sonnet.

Each approach maps the headers in data/header_labels.yaml, and the answers are scored against
the labels. The set is small and synthetic, so the numbers describe this set, not real files.
Jev runs in replay by default: a header with no recording is "not recorded", counted in its
own column and never as a wrong or missing mapping. Costs are estimates from token counts.
"""

import json
import os
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Final, Literal

import yaml

from agency_schema.models import TABLE_MODELS
from agency_schema.outputs import JevMode
from intake.config import (
    BENCH_JEV_MIN_CONFIDENCE,
    BENCH_SONNET_MAX_TOKENS,
    BENCH_SONNET_MODEL,
    SONNET_USD_PER_MTOK_IN,
    SONNET_USD_PER_MTOK_OUT,
)
from intake.mapping.headers import SOURCE_TABLES
from intake.mapping.synonyms import COMPOSITE_FIELDS, load_synonyms
from jev_client import CassetteMiss, ChoiceAnswer, ChoiceQuestion, JevClient, JevRequest
from jev_client.cassettes import cassette_path
from jev_client.types import JevResponse

LABELS_PATH = Path(__file__).resolve().parent / "data" / "header_labels.yaml"
REPO_ROOT = Path(__file__).resolve().parents[4]
DOC_PATH = REPO_ROOT / "docs" / "benchmark-header-mapping.md"
README_PATH = REPO_ROOT / "README.md"
START, END = "<!-- benchmark:start -->", "<!-- benchmark:end -->"
NONE: Final = "none"  # the column holds no canonical field (or the approach left it unmapped)
NOT_RECORDED: Final = "not recorded"  # replay had no recording for this header
JEV_INSTRUCTIONS = (
    "A column header from an insurance agency's source export is given with the kind of "
    "export. Which canonical field does the column hold? Choose none if it holds none of them."
)
_MICRO = Decimal("0.000001")


@dataclass(frozen=True)
class LabeledHeader:
    kind: str  # crm, enrollment, statement, roster_agents, or roster_rts
    header: str
    expected: str  # "table.field", or "none"
    origin: Literal["fixture", "synthetic"]


def options(kind: str) -> tuple[str, ...]:
    """Every canonical field a header from this kind of source can map to."""
    out: list[str] = []
    for table in SOURCE_TABLES[kind]:
        fields = [f for f in TABLE_MODELS[table].model_fields if f != "lineage"]
        fields += [c for c, parts in COMPOSITE_FIELDS.items() if set(parts) <= set(fields)]
        out += [f"{table}.{f}" for f in fields]
    return tuple(out)


def load_labels(path: Path = LABELS_PATH) -> tuple[LabeledHeader, ...]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    items: list[LabeledHeader] = []
    for origin in ("fixture", "synthetic"):
        for kind, headers in raw[origin].items():
            for header, expected in headers.items():
                if expected != NONE and expected not in options(kind):
                    raise ValueError(f"labels: {header!r} in {kind} maps to unknown {expected}")
                items.append(LabeledHeader(kind, str(header), str(expected), origin))
    return tuple(items)


@dataclass(frozen=True)
class Metrics:
    total: int
    scored: int  # total minus not recorded
    correct: int
    wrong: int  # mapped to the wrong field, or mapped a column that holds none
    missed: int  # left unmapped although the column holds a field
    not_recorded: int
    mapped: int

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.scored if self.scored else None

    @property
    def coverage(self) -> float | None:
        return self.mapped / self.scored if self.scored else None


def score(items: Sequence[LabeledHeader], guesses: Sequence[str]) -> Metrics:
    counts = {"correct": 0, "wrong": 0, "missed": 0, "not_recorded": 0, "mapped": 0}
    for item, guess in zip(items, guesses, strict=True):
        if guess == NOT_RECORDED:
            counts["not_recorded"] += 1
            continue
        counts["mapped"] += guess != NONE
        if guess == item.expected:
            counts["correct"] += 1
        else:
            counts["missed" if guess == NONE else "wrong"] += 1
    return Metrics(total=len(items), scored=len(items) - counts["not_recorded"], **counts)


@dataclass(frozen=True)
class ArmResult:
    name: str
    guesses: tuple[str, ...]  # one per labeled header, in order; empty when skipped
    skipped: str | None
    calls: int
    cost_usd: Decimal  # an estimate from token counts, not a bill
    wall_s: float
    latencies_s: tuple[float, ...]  # network calls only; empty in replay
    timing_note: str


def synonym_guess(item: LabeledHeader) -> str:
    target = load_synonyms().match(item.header, SOURCE_TABLES[item.kind]).target
    return str(target) if target else NONE


def run_synonyms(items: Sequence[LabeledHeader]) -> ArmResult:
    start = time.perf_counter()
    guesses = tuple(synonym_guess(i) for i in items)
    wall = time.perf_counter() - start
    return ArmResult("Synonyms only", guesses, None, 0, Decimal(0), wall, (), "no model calls")


def jev_request(item: LabeledHeader) -> JevRequest:
    """One choice question per header. Only the header and source kind are sent, no values."""
    criteria: dict[str, Any] = {o: None for o in options(item.kind)}
    criteria[NONE] = "The column holds none of the listed fields"
    question = ChoiceQuestion(type="choice", instructions=JEV_INSTRUCTIONS, criteria=criteria)
    return JevRequest(
        state={"header": item.header, "source": item.kind}, questions={"field": question}
    )


def run_jev(items: Sequence[LabeledHeader], client: JevClient, cassette_dir: Path) -> ArmResult:
    latencies: list[float] = []

    def ask(item: LabeledHeader) -> str:
        request = jev_request(item)
        recorded = cassette_path(cassette_dir, request.body()).exists()
        start = time.perf_counter()
        try:
            reply = client.ask(request)
        except CassetteMiss:
            return NOT_RECORDED
        if client.mode == JevMode.LIVE or (client.mode == JevMode.RECORD and not recorded):
            latencies.append(time.perf_counter() - start)
        if not isinstance(reply, JevResponse):
            return NOT_RECORDED  # Jev off or over budget: no answer to score
        answer = reply.answers["field"]
        assert isinstance(answer, ChoiceAnswer)  # the client checked it answers the question
        if answer.choice == NONE or answer.confidence < BENCH_JEV_MIN_CONFIDENCE:
            return NONE
        return answer.choice

    start = time.perf_counter()
    guesses = _after_synonyms(items, ask)
    wall = time.perf_counter() - start
    note = "replay reads recordings, so latency is not measured"
    if client.mode in (JevMode.LIVE, JevMode.RECORD):
        note = f"{client.mode.value} mode, {len(latencies)} network calls timed"
    usage = client.usage
    return ArmResult(
        "Synonyms then Jev",
        guesses,
        None,
        usage.calls,
        usage.estimated_cost_usd,
        wall,
        tuple(latencies),
        note,
    )


SonnetAsk = Callable[[LabeledHeader], tuple[str, int, int]]  # guess, input and output tokens


def sonnet_cost(input_tokens: int, output_tokens: int) -> Decimal:
    raw = (
        Decimal(input_tokens) * SONNET_USD_PER_MTOK_IN
        + Decimal(output_tokens) * SONNET_USD_PER_MTOK_OUT
    )
    return (raw / Decimal(1_000_000)).quantize(_MICRO, rounding=ROUND_HALF_UP)


def run_sonnet(items: Sequence[LabeledHeader], ask: SonnetAsk | None, skipped: str) -> ArmResult:
    name = "Synonyms then Sonnet"
    if ask is None:
        return ArmResult(name, (), skipped, 0, Decimal(0), 0.0, (), skipped)
    latencies: list[float] = []
    tokens = [0, 0]

    def timed(item: LabeledHeader) -> str:
        start = time.perf_counter()
        guess, tokens_in, tokens_out = ask(item)
        latencies.append(time.perf_counter() - start)
        tokens[0] += tokens_in
        tokens[1] += tokens_out
        return guess

    start = time.perf_counter()
    guesses = _after_synonyms(items, timed)
    wall = time.perf_counter() - start
    cost = sonnet_cost(*tokens)
    note = f"live calls to {BENCH_SONNET_MODEL}"
    return ArmResult(name, guesses, None, len(latencies), cost, wall, tuple(latencies), note)


def _after_synonyms(
    items: Sequence[LabeledHeader], ask: Callable[[LabeledHeader], str]
) -> tuple[str, ...]:
    """Synonyms decide first; only a header they leave unmapped goes to the model."""
    return tuple(g if (g := synonym_guess(i)) != NONE else ask(i) for i in items)


def anthropic_ask() -> SonnetAsk:  # pragma: no cover - spends money, never runs in tests
    """Ask Sonnet through the Anthropic API with a strict JSON answer. Header text only."""
    import anthropic

    client = anthropic.Anthropic()

    def ask(item: LabeledHeader) -> tuple[str, int, int]:
        choices = [*options(item.kind), NONE]
        schema = {
            "type": "object",
            "properties": {"field": {"type": "string", "enum": choices}},
            "required": ["field"],
            "additionalProperties": False,
        }
        prompt = (
            f"A column header from an insurance agency's {item.kind} export reads "
            f"{json.dumps(item.header)}. Which canonical field does the column hold? "
            "Answer none if it holds none of the listed fields."
        )
        response = client.messages.create(
            model=BENCH_SONNET_MODEL,
            max_tokens=BENCH_SONNET_MAX_TOKENS,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        )
        guess = NONE
        text = next((b.text for b in response.content if b.type == "text"), "")
        if response.stop_reason == "end_turn":
            try:
                guess = str(json.loads(text).get("field", NONE))
            except ValueError:
                guess = NONE
        guess = guess if guess in choices else NONE
        return guess, response.usage.input_tokens, response.usage.output_tokens

    return ask


@dataclass(frozen=True)
class BenchResult:
    items: tuple[LabeledHeader, ...]
    arms: tuple[ArmResult, ...]


def run_benchmark(
    items: Sequence[LabeledHeader],
    jev: JevClient,
    cassette_dir: Path,
    sonnet: SonnetAsk | None,
    sonnet_skipped: str,
) -> BenchResult:
    arms = (
        run_synonyms(items),
        run_jev(items, jev, cassette_dir),
        run_sonnet(items, sonnet, sonnet_skipped),
    )
    return BenchResult(tuple(items), arms)


def sonnet_skip_reason(opted_in: bool) -> str | None:
    """None when the Sonnet arm may run: a key is set and the caller opted in to the spend."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "skipped: no key"
    if not opted_in:
        return "skipped: pass --sonnet to spend"
    return None


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _per_thousand(arm: ArmResult, total: int) -> str:
    if arm.calls == 0:
        return "$0"
    return f"${arm.cost_usd * 1000 / total:.4f} (estimate)"


def table_rows(result: BenchResult) -> list[str]:
    rows = [
        "| Approach | Accuracy | Coverage | Wrong mappings | Not recorded | Model calls "
        "| Est. cost per 1,000 headers |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm in result.arms:
        if arm.skipped:
            rows.append(f"| {arm.name} | {arm.skipped} | n/a | n/a | n/a | 0 | n/a |")
            continue
        m = score(result.items, arm.guesses)
        accuracy = f"{_pct(m.accuracy)} ({m.correct} of {m.scored})"
        coverage, cost = _pct(m.coverage), _per_thousand(arm, m.total)
        if arm.calls == 0 and m.not_recorded:
            # Only synonym answers were scored, so a percentage here would credit the model.
            accuracy, coverage, cost = "not measured: no recordings yet", "n/a", "n/a"
        cells = [arm.name, accuracy, coverage, str(m.wrong), str(m.not_recorded), str(arm.calls)]
        rows.append("| " + " | ".join([*cells, cost]) + " |")
    return rows


def render_readme_block(result: BenchResult) -> str:
    fixture = sum(i.origin == "fixture" for i in result.items)
    lines = [
        START,
        f"Header mapping benchmark on {len(result.items)} labeled headers ({fixture} from the "
        f"fixture files, {len(result.items) - fixture} synthetic variants), Jev in replay. "
        "Small synthetic set; method and caveats in "
        "[docs/benchmark-header-mapping.md](docs/benchmark-header-mapping.md).",
        "",
        *table_rows(result),
        END,
    ]
    return "\n".join(lines)


def update_readme(text: str, block: str) -> str:
    head, sep, rest = text.partition(START)
    _, sep2, tail = rest.partition(END)
    if not sep or not sep2:
        raise ValueError("README.md needs the benchmark:start and benchmark:end markers")
    return head + block + tail


def _latency(arm: ArmResult) -> str:
    if len(arm.latencies_s) < 2:
        return f"not measured ({arm.timing_note})"
    cuts = statistics.quantiles(arm.latencies_s, n=100)
    return f"p50 {cuts[49]:.2f} s, p95 {cuts[94]:.2f} s"


def render_doc(result: BenchResult) -> str:
    fixture = sum(i.origin == "fixture" for i in result.items)
    total = len(result.items)
    out = [
        "# Header mapping benchmark",
        "",
        "Generated by `cd engine && uv run intake bench header-mapping`. Do not edit by hand.",
        "",
        "How well does each approach turn a messy column header into the right canonical field?",
        f"The labeled set has {total} headers: all {fixture} distinct headers in the agency-a "
        f"fixture files and {total - fixture} synthetic variants written for this benchmark, some "
        "of which hold no canonical field. Every header in it is synthetic and the set is small, "
        "so these numbers describe this set only, not real agency files.",
        "",
        *table_rows(result),
        "",
        "## How to read it",
        "",
        "- **Accuracy:** right answers out of the headers scored. Leaving a column unmapped is "
        "right when it holds no canonical field.",
        "- **Coverage:** the share of scored headers mapped to some field, right or wrong.",
        "- **Wrong mappings:** a header mapped to the wrong field. This is the costly mistake: "
        "data lands in the wrong place quietly, where an unmapped column is at least flagged.",
        "- **Not recorded:** Jev runs in replay here, reading saved answers (cassettes). A header "
        "with no saved answer is not scored at all. It is never counted as wrong or missed, "
        "which would make Jev look worse than it is. With recordings for only some headers, "
        "accuracy covers the scored headers only, so compare rows with that in mind.",
        "- **Est. cost:** estimated from the token counts in the replies, at published prices: "
        "Jev $0.042 per million input tokens, output free (docs/jev.md); Sonnet "
        f"(`{BENCH_SONNET_MODEL}`) $2 per million input and $10 per million output tokens "
        "(Anthropic's price table, checked 2026-10-04). Estimates, not bills.",
        "",
        "## Method",
        "",
        "Synonyms come first in every approach, as in the pipeline: the header is normalized and "
        "looked up in `engine/src/intake/data/synonyms.yaml`. Only a header the synonyms leave "
        "unmapped goes to a model. Jev gets one pick-one question per header with every field of "
        "that source's tables plus none as options. It sends the header text and source kind "
        f"only, never values. An answer below {BENCH_JEV_MIN_CONFIDENCE} confidence counts as "
        "unmapped, as in SPEC. Sonnet gets the same options as a strict JSON answer.",
        "",
        "| Approach | Model calls | Wall time | Latency |",
        "|---|---|---|---|",
    ]
    for arm in result.arms:
        if arm.skipped:
            out.append(f"| {arm.name} | n/a | n/a | {arm.skipped} |")
        else:
            out.append(f"| {arm.name} | {arm.calls} | {arm.wall_s:.2f} s | {_latency(arm)} |")
    out += [
        "",
        "Wall time is for this machine and this run. In replay it measures reading files, not "
        "the network, so it says nothing about Jev's real speed.",
        "",
        "The Sonnet arm runs only with `ANTHROPIC_API_KEY` set and `--sonnet` passed, because it "
        "spends money. It makes live calls every time; nothing is recorded.",
        "",
        "## Recording Jev answers",
        "",
        "Recording spends money, so Alex approves each run first. Then one command records "
        "every missing answer and rewrites this page and the README table:",
        "",
        "```bash",
        "cd engine && uv run intake bench header-mapping --jev record --approve-spend",
        "```",
        "",
        "## Every header",
        "",
        "| Source | Header | Expected | Synonyms | Jev | Sonnet |",
        "|---|---|---|---|---|---|",
    ]
    columns = [arm.guesses or ("skipped",) * total for arm in result.arms]
    for n, item in enumerate(result.items):
        cells = [_cell(col[n], item.expected) for col in columns]
        out.append(
            f"| {item.kind} | `{item.header}` | {item.expected} | " + " | ".join(cells) + " |"
        )
    return "\n".join(out) + "\n"


def _cell(guess: str, expected: str) -> str:
    if guess in (NOT_RECORDED, "skipped") or guess == expected:
        return "right" if guess == expected else guess
    return f"**{guess}**"


def write_outputs(result: BenchResult, doc: Path = DOC_PATH, readme: Path = README_PATH) -> None:
    doc.write_text(render_doc(result), encoding="utf-8", newline="\n")
    text = readme.read_text(encoding="utf-8")
    readme.write_text(
        update_readme(text, render_readme_block(result)), encoding="utf-8", newline="\n"
    )
