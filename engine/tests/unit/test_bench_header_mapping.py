"""PR 17: the header mapping benchmark. Metrics on a fixed set match hand-computed values."""

from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agency_schema.outputs import JevMode
from intake.bench.header_mapping import (
    END,
    NONE,
    NOT_RECORDED,
    START,
    LabeledHeader,
    Metrics,
    jev_request,
    load_labels,
    render_doc,
    render_readme_block,
    run_benchmark,
    run_jev,
    run_sonnet,
    run_synonyms,
    score,
    sonnet_skip_reason,
    update_readme,
)
from intake.cli import app
from intake.ingest import ingest
from intake.mapping.headers import mapping_key
from intake.readers import LINEAGE_COLUMN
from jev_client import JevClient
from jev_client.cassettes import save_cassette
from jev_client.client import DEFAULT_CASSETTE_DIR

DROP = Path(__file__).resolve().parents[3] / "fixtures" / "agency-a" / "drop"

# Six headers, worked out by hand:
# 1 Mbr DOB: synonyms map it.            4 Paid: synonyms miss; Jev has no recording.
# 2 Birth Dt: synonyms miss; Jev right.  5 Email: synonyms map it.
# 3 Lead Source (holds none): synonyms leave it; Jev maps it wrongly at 0.70.
# 6 Cust Ref: synonyms miss; Jev answers at 0.40, under the 0.60 cutoff, so it stays unmapped.
FIXED = (
    LabeledHeader("crm", "Mbr DOB", "clients.dob", "synthetic"),
    LabeledHeader("enrollment", "Birth Dt (mm/dd/yy)", "clients.dob", "synthetic"),
    LabeledHeader("crm", "Lead Source", NONE, "synthetic"),
    LabeledHeader("statement", "Paid", "commission_lines.paid_date", "synthetic"),
    LabeledHeader("crm", "Email", "clients.email", "synthetic"),
    LabeledHeader("crm", "Cust Ref", "clients.client_id", "synthetic"),
)
JEV_ANSWERS = {1: ("clients.dob", 0.93), 2: ("clients.notes", 0.70), 5: ("clients.client_id", 0.40)}
SONNET_ANSWERS = {
    "Birth Dt (mm/dd/yy)": "clients.dob",
    "Lead Source": NONE,
    "Paid": "commission_lines.paid_date",
    "Cust Ref": "clients.client_id",
}


def _record_fixed(cassette_dir: Path) -> None:
    for n, (choice, confidence) in JEV_ANSWERS.items():
        response = {
            "model": "jev-1.13.0",
            "answers": {
                "field": {
                    "type": "choice",
                    "choice": choice,
                    "probabilities": {choice: confidence},
                    "confidence": confidence,
                }
            },
            "usage": {"input_tokens": 1000, "output_tokens": 0},
        }
        save_cassette(cassette_dir, jev_request(FIXED[n]).body(), response)


def _replay(cassette_dir: Path) -> JevClient:
    return JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=cassette_dir)


def test_fixed_set_synonyms_match_hand_counts() -> None:
    arm = run_synonyms(FIXED)
    m = score(FIXED, arm.guesses)
    assert m == Metrics(total=6, scored=6, correct=3, wrong=0, missed=3, not_recorded=0, mapped=2)
    assert m.accuracy == 0.5
    assert m.coverage == pytest.approx(2 / 6)
    assert arm.cost_usd == 0


def test_fixed_set_jev_match_hand_counts(tmp_path: Path) -> None:
    _record_fixed(tmp_path)
    arm = run_jev(FIXED, _replay(tmp_path), tmp_path)
    assert arm.guesses == (
        "clients.dob",
        "clients.dob",
        "clients.notes",
        NOT_RECORDED,
        "clients.email",
        NONE,
    )
    m = score(FIXED, arm.guesses)
    assert m == Metrics(total=6, scored=5, correct=3, wrong=1, missed=1, not_recorded=1, mapped=4)
    assert m.accuracy == 0.6
    assert m.coverage == 0.8
    assert arm.calls == 3
    assert arm.cost_usd == Decimal("0.000126")  # 3,000 input tokens at $0.042 per million
    assert arm.latencies_s == ()  # replay never times calls


def test_fixed_set_sonnet_match_hand_counts() -> None:
    def fake(item: LabeledHeader) -> tuple[str, int, int]:
        return SONNET_ANSWERS[item.header], 1000, 20

    arm = run_sonnet(FIXED, fake, "unused")
    m = score(FIXED, arm.guesses)
    assert m == Metrics(total=6, scored=6, correct=6, wrong=0, missed=0, not_recorded=0, mapped=5)
    assert arm.calls == 4
    assert arm.cost_usd == Decimal("0.008800")  # 4 x (1,000 x $2 + 20 x $10) per million


def test_labels_cover_every_fixture_header() -> None:
    found = set()
    for table in ingest(DROP, run_id="bench").tables:
        key = mapping_key(table.source, table.sheet)
        kind = "statement" if key.startswith("statement_") else key
        found |= {(kind, c) for c in table.frame.columns if c != LINEAGE_COLUMN}
    labels = load_labels()
    fixture = {(i.kind, i.header) for i in labels if i.origin == "fixture"}
    assert fixture == found
    assert len(fixture) == 79
    assert sum(i.origin == "synthetic" for i in labels) >= 40


def test_full_replay_run_has_three_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert sonnet_skip_reason(opted_in=True) == "skipped: no key"
    labels = load_labels()
    result = run_benchmark(
        labels, _replay(DEFAULT_CASSETTE_DIR), DEFAULT_CASSETTE_DIR, None, "skipped: no key"
    )
    block = render_readme_block(result)
    rows = [line for line in block.splitlines() if line.startswith("| ") and "Approach" not in line]
    assert [r.split(" | ")[0] for r in rows] == [
        "| Synonyms only",
        "| Synonyms then Jev",
        "| Synonyms then Sonnet",
    ]
    assert "skipped: no key" in rows[2]
    assert "Header mapping benchmark" in render_doc(result)


def test_jev_is_at_least_as_accurate_where_it_answered() -> None:
    labels = load_labels()
    synonyms = run_synonyms(labels).guesses
    jev = run_jev(labels, _replay(DEFAULT_CASSETTE_DIR), DEFAULT_CASSETTE_DIR).guesses
    answered = [n for n, g in enumerate(jev) if g != NOT_RECORDED]
    subset = [labels[n] for n in answered]
    jev_m = score(subset, [jev[n] for n in answered])
    syn_m = score(subset, [synonyms[n] for n in answered])
    # Jev only sees headers the synonyms left unmapped, and synonym answers never change.
    assert jev_m.correct >= syn_m.correct


def test_update_readme_replaces_only_between_markers() -> None:
    text = f"intro\n{START}\nold\n{END}\noutro\n"
    once = update_readme(text, f"{START}\nnew\n{END}")
    assert once == f"intro\n{START}\nnew\n{END}\noutro\n"
    assert update_readme(once, f"{START}\nnew\n{END}") == once
    with pytest.raises(ValueError, match="markers"):
        update_readme("no markers", "x")


def test_cli_runs_in_replay_without_writing() -> None:
    result = CliRunner().invoke(
        app, ["bench", "header-mapping", "--no-write"], env={"ANTHROPIC_API_KEY": ""}
    )
    assert result.exit_code == 0, result.output
    assert "Synonyms then Jev" in result.output
    assert "skipped: no key" in result.output


def test_cli_refuses_record_without_approval() -> None:
    result = CliRunner().invoke(app, ["bench", "header-mapping", "--jev", "record", "--no-write"])
    assert result.exit_code != 0
    assert "spends money" in result.output
