"""Command line entry point for the intake pipeline."""

import json
import math
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from agency_schema import json_schema
from agency_schema.outputs import JevMode, RunStatus
from agency_schema.typescript import render_typescript
from intake import __version__
from intake.config import JEV_CHARS_PER_TOKEN
from intake.finance_cli import app as finance_local_app
from intake.integration_cli import app as integration_app
from intake.mapping.jev_mapping import MAPPING_CASSETTES
from intake.source_readiness_cli import app as readiness_app
from jev_client import JevClient

# engine/src/intake/cli.py -> repo root
DASHBOARD_TYPES = Path(__file__).resolve().parents[3] / "dashboard" / "lib" / "types.ts"

app = typer.Typer(help="Agency intake pipeline. Synthetic data only.", no_args_is_help=True)
app.add_typer(integration_app, name="integration")
app.add_typer(readiness_app, name="readiness")
app.add_typer(finance_local_app, name="finance-local")


@app.callback()
def main() -> None:
    """Keep the app a command group so subcommands arrive cleanly in later PRs."""


@app.command()
def version() -> None:
    """Print the engine version."""
    typer.echo(__version__)


@app.command()
def schema(
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the JSON Schema (default).")
    ] = False,
    ts: Annotated[
        bool, typer.Option("--ts", help="Write the dashboard's TypeScript types.")
    ] = False,
    out: Annotated[Path, typer.Option(help="Where --ts writes.")] = DASHBOARD_TYPES,
) -> None:
    """Export the schema of the tables, exceptions, and run output files."""
    if as_json and ts:
        raise typer.BadParameter("pass --json or --ts, not both")
    if ts:
        out.write_text(render_typescript())
        typer.echo(f"wrote {out}")
    else:
        typer.echo(json.dumps(json_schema("serialization"), indent=2))


@app.command()
def rules(
    md: Annotated[bool, typer.Option("--md", help="Print docs/rules.md as Markdown.")] = False,
) -> None:
    """List the registered rules, or print the Markdown catalog with --md."""
    from agency_schema.registry import catalog
    from intake.rules.docs import render_rules_md

    if md:
        typer.echo(render_rules_md(), nl=False)
        return
    for m in catalog():
        typer.echo(f"{m.rule_id}  {m.severity:<8}  {m.description}")


@app.command()
def diff(
    run_a: Annotated[Path, typer.Argument(help="The earlier run folder.")],
    run_b: Annotated[Path, typer.Argument(help="The later run folder.")],
) -> None:
    """Print what changed between two runs: status, exceptions, and tie-out differences."""
    from pydantic import ValidationError

    from intake.diff import diff_runs

    try:
        lines = diff_runs(run_a, run_b)
    except (ValueError, ValidationError) as error:
        typer.echo(f"Could not compare these runs. {error}", err=True)
        raise typer.Exit(1) from None
    typer.echo("\n".join(lines))


@app.command("finance-review")
def finance_review(
    statement: Annotated[Path, typer.Option(help="Synthetic statement package JSON.")],
    mapping: Annotated[Path, typer.Option(help="Versioned finance mapping JSON.")],
    output_format: Annotated[str, typer.Option("--format", help="json or csv.")] = "json",
) -> None:
    """Print a neutral finance review; never post entries or assign customer identity."""
    from intake.revenue import (
        RevenueMapping,
        StatementPackage,
        classify_statement,
        review_csv,
        review_json,
    )

    if output_format not in ("json", "csv"):
        raise typer.BadParameter("--format must be json or csv")
    try:
        package = StatementPackage.model_validate_json(statement.read_text())
        rules = RevenueMapping.model_validate_json(mapping.read_text())
        review = classify_statement(package, rules)
    except (OSError, ValueError):
        # Validation errors can contain source values; keep rejected input out of logs.
        typer.echo("Finance review refused: invalid or unreadable statement or mapping.", err=True)
        raise typer.Exit(2) from None
    typer.echo(review_csv(review) if output_format == "csv" else review_json(review), nl=False)


@app.command("finance-ledger")
def finance_ledger(
    receipts: Annotated[Path, typer.Option(help="Synthetic ordered receipt batch JSON.")],
    mapping: Annotated[Path, typer.Option(help="Versioned mapping for this carrier.")],
) -> None:
    """Print active revenue and unresolved corrections without counting duplicate receipts."""
    from intake.revenue import RevenueMapping
    from intake.revenue_ledger import ReceiptBatch, reconcile_receipts

    try:
        batch = ReceiptBatch.model_validate_json(receipts.read_text())
        rules = RevenueMapping.model_validate_json(mapping.read_text())
        ledger = reconcile_receipts(batch.receipts, rules)
    except (OSError, ValueError):
        typer.echo("Finance ledger refused: invalid receipts or mapping.", err=True)
        raise typer.Exit(2) from None
    typer.echo(ledger.model_dump_json(indent=2))


def _clock(as_of: str | None) -> datetime | None:
    if as_of is None:
        return None
    try:
        clock = datetime.fromisoformat(as_of)
    except ValueError as error:
        raise typer.BadParameter(f"--as-of is not a date and time: {as_of}") from error
    if clock.tzinfo is None:
        raise typer.BadParameter("--as-of needs a time zone, for example 2026-10-01T09:00:00Z")
    return clock


@app.command("run")
def run_command(
    drop: Annotated[Path, typer.Option("--in", help="The drop folder (holds manifest.json).")],
    out: Annotated[Path, typer.Option("--out", help="The run folder; its name is the run id.")],
    jev: Annotated[
        JevMode, typer.Option(help="replay (recorded answers, the default) or off (no model).")
    ] = JevMode.REPLAY,
    as_of: Annotated[
        str | None, typer.Option("--as-of", help="Freeze the clock, e.g. 2026-10-01T09:00:00Z.")
    ] = None,
    overwrite: Annotated[bool, typer.Option(help="Replace an existing run folder.")] = False,
) -> None:
    """Run the whole pipeline on one drop. Exits 1 when the run FAILED, 2 when it cannot start."""
    from intake.run.pipeline import RunOptions, RunRefused, run

    if jev not in (JevMode.REPLAY, JevMode.OFF):
        raise typer.BadParameter(
            "intake run uses replay or off; recording is intake jev record-run"
        )
    try:
        result = run(RunOptions(drop, out, jev, _clock(as_of), overwrite))
    except RunRefused as refused:
        typer.echo(str(refused), err=True)
        raise typer.Exit(2) from refused
    by_severity = Counter(r.severity.value.lower() for r in result.records)
    typer.echo(f"{result.status.value}: {result.run_dir}")
    typer.echo(
        "Exceptions: "
        + ", ".join(f"{by_severity[s]} {s}" for s in ("blocker", "error", "warning", "info"))
    )
    usage = result.client.usage
    typer.echo(
        f"Jev {usage.mode.value}: {usage.calls} calls, estimated ${usage.estimated_cost_usd}; "
        f"{len(result.client.misses)} questions had no recording and went to a person"
    )
    if result.enrollment is not None:
        e = result.enrollment
        typer.echo(
            f"Enrollment birth dates vs CRM: {e.agree} of {e.compared} agree, "
            f"{len(e.disagree)} differ, {e.unreadable} unreadable"
        )
    if result.score is not None:
        typer.echo(
            f"Detection: false positives {result.score.summary.false_positive_rate:.4%} of "
            f"{result.score.summary.clean_rows:,} clean rows (scorecard.json detection.clean_rows)"
        )
    if result.status == RunStatus.FAILED:
        raise typer.Exit(1)


bench_app = typer.Typer(help="Benchmarks on the synthetic fixtures.", no_args_is_help=True)
app.add_typer(bench_app, name="bench")


@bench_app.command("header-mapping")
def bench_header_mapping(
    jev: Annotated[JevMode, typer.Option(help="replay (default) costs nothing.")] = JevMode.REPLAY,
    approve_spend: Annotated[
        bool, typer.Option("--approve-spend", help="Allow --jev live or record (Alex approves).")
    ] = False,
    sonnet: Annotated[
        bool, typer.Option("--sonnet", help="Run the Sonnet arm (needs ANTHROPIC_API_KEY).")
    ] = False,
    write: Annotated[
        bool, typer.Option(help="Rewrite the benchmark doc and the README table.")
    ] = True,
) -> None:
    """Score synonyms, synonyms then Jev, and synonyms then Sonnet on the labeled headers."""
    from intake.bench import header_mapping as bench
    from jev_client import JevClient, SpendNotApproved
    from jev_client.client import DEFAULT_CASSETTE_DIR

    try:
        client = JevClient(
            mode=jev, api_key=os.environ.get("TYPESAFE_API_KEY"), allow_spend=approve_spend
        )
    except SpendNotApproved as error:
        typer.echo(str(error))
        raise typer.Exit(2) from error
    skipped = bench.sonnet_skip_reason(sonnet)
    ask = bench.anthropic_ask() if skipped is None else None
    result = bench.run_benchmark(
        bench.load_labels(), client, DEFAULT_CASSETTE_DIR, ask, skipped or ""
    )
    typer.echo("\n".join(bench.table_rows(result)))
    if write:
        bench.write_outputs(result)
        typer.echo(f"wrote {bench.DOC_PATH} and the README table")


mapping_app = typer.Typer(help="Saved header mappings beside a drop.", no_args_is_help=True)
app.add_typer(mapping_app, name="mapping")


@mapping_app.command("apply")
def mapping_apply(
    decisions: Annotated[Path, typer.Argument(help="The decisions file the dashboard saved.")],
    run_dir: Annotated[Path, typer.Option("--run", help="The run folder that was reviewed.")],
    drop: Annotated[Path, typer.Option("--in", help="That run's drop folder.")],
) -> None:
    """Save a reviewer's mapping decisions into mapping/<source>.yaml beside the drop.

    Refused, with nothing written, unless every decision matches the run's mapping_review.json
    and the drop's files. If a write still fails part way, it lists the files already written.
    The file is a reviewer's note, not an authenticated approval.
    """
    from intake.mapping.apply import ApplyRefused, apply_decisions

    try:
        summary = apply_decisions(decisions, run_dir, drop)
    except ApplyRefused as refused:
        if not refused.written:
            typer.echo(f"Refused: {refused}. Nothing was written.", err=True)
            raise typer.Exit(2) from None
        typer.echo(f"Stopped: {refused}. These files were already written:", err=True)
        for path in refused.written:
            typer.echo(f"wrote {path}", err=True)
        typer.echo(
            "Each one's previous version, if it had one, is in the matching .yaml.prev file. "
            "The other files were not changed.",
            err=True,
        )
        raise typer.Exit(2) from None
    typer.echo(
        f"Applied: {summary.approved} approved, {summary.corrected} corrected, "
        f"{summary.ignored} ignored. Columns with no decision stay unresolved."
    )
    for path in summary.files:
        typer.echo(f"wrote {path}")
    typer.echo("This is a reviewer's note, not an authenticated approval.")


jev_app = typer.Typer(
    help="Jev (TypeSafe) recordings. Recording spends money.", no_args_is_help=True
)
app.add_typer(jev_app, name="jev")
HANDMADE_MODEL = "handmade-placeholder"  # the response model in cassettes written by hand


def _record_client(cassettes: Path) -> JevClient:
    return JevClient.from_env(allow_spend=True, cassette_dir=cassettes)


@jev_app.command("record-mapping")
def record_mapping(
    drop: Annotated[Path, typer.Option(help="A fixture folder or its drop/ folder.")],
    cassettes: Annotated[Path, typer.Option(help="Where cassettes go.")] = MAPPING_CASSETTES,
) -> None:
    """Record the header and enum cassettes for a drop. Needs JEV_MODE=record; spends money."""
    from intake.mapping.enums import fill_drop
    from intake.mapping.jev_mapping import Asker
    from jev_client import canonical_json, estimate_cost_usd
    from jev_client.cassettes import cassette_path

    if os.environ.get("JEV_MODE") != "record":
        typer.echo("Refusing: set JEV_MODE=record, and only after Alex approves the spend.")
        raise typer.Exit(2)
    drop = drop / "drop" if (drop / "drop").is_dir() else drop
    now = datetime.now(UTC)
    plan = Asker(None)  # collects the requests without sending any
    with tempfile.TemporaryDirectory() as tmp:
        fill_drop(drop, Path(tmp), now, plan)
    bodies = [r.body() for r in plan.requests.values()]
    tokens = sum(math.ceil(len(canonical_json(b).encode()) / JEV_CHARS_PER_TOKEN) for b in bodies)
    typer.echo(
        f"{len(bodies)} requests ({plan.asked} asked, duplicates sent once), "
        f"about {tokens} input tokens, estimated cost ${estimate_cost_usd(tokens)}"
    )
    for body in bodies:
        path = cassette_path(cassettes, body)
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8"))["response"]["model"] == HANDMADE_MODEL:
                path.unlink()  # a hand-made stand-in; the real answer replaces it
    client = _record_client(cassettes)
    asker = Asker(client)
    with tempfile.TemporaryDirectory() as tmp:
        fill_drop(drop, Path(tmp), now, asker)
    usage = client.usage
    typer.echo(
        f"Done. Answers {usage.calls}, input tokens {usage.input_tokens}, "
        f"estimated cost ${usage.estimated_cost_usd}, "
        f"invalid answers {asker.invalid} (not used, a person decides)"
    )


@jev_app.command("record-run")
def record_run(
    drop: Annotated[Path, typer.Option(help="A fixture folder or its drop/ folder.")],
    as_of: Annotated[str, typer.Option("--as-of", help="The run clock.")] = "2026-10-01T09:00:00Z",
) -> None:
    """Record the triage and PII cassettes a real run asks for. Needs JEV_MODE=record; spends money.

    First a replay run finds the questions with no recording and prints how many and the
    estimated cost. Then a record run asks only those (recorded answers are reused).
    """
    from intake.run.jev import RunJevClient, estimate_cost, estimate_tokens
    from intake.run.pipeline import RunOptions, run

    if os.environ.get("JEV_MODE") != "record":
        typer.echo("Refusing: set JEV_MODE=record, and only after Alex approves the spend.")
        raise typer.Exit(2)
    drop = drop / "drop" if (drop / "drop").is_dir() else drop
    clock = _clock(as_of)
    with tempfile.TemporaryDirectory() as tmp:
        plan = run(RunOptions(drop, Path(tmp) / "plan", JevMode.REPLAY, clock)).client.misses
    typer.echo(
        f"{len(plan)} requests to record, about {estimate_tokens(plan)} input tokens, "
        f"estimated cost ${estimate_cost(plan)}"
    )
    if not plan:
        return
    key = os.environ.get("TYPESAFE_API_KEY")  # read here, never printed
    client = RunJevClient(mode=JevMode.RECORD, api_key=key, allow_spend=True)
    with tempfile.TemporaryDirectory() as tmp:
        run(RunOptions(drop, Path(tmp) / "record", JevMode.RECORD, clock, client=client))
    usage = client.usage
    typer.echo(
        f"Done. Answers {usage.calls}, input tokens {usage.input_tokens}, "
        f"estimated cost ${usage.estimated_cost_usd}, budget tripped {usage.budget_tripped}, "
        f"invalid answers {usage.invalid_answers} (not used, a person decides)"
    )
