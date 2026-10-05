"""Command line entry point for the intake pipeline. Commands arrive in later PRs."""

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from agency_schema import json_schema
from agency_schema.outputs import JevMode
from agency_schema.typescript import render_typescript
from intake import __version__

# engine/src/intake/cli.py -> repo root
DASHBOARD_TYPES = Path(__file__).resolve().parents[3] / "dashboard" / "lib" / "types.ts"

app = typer.Typer(help="Agency intake pipeline. Synthetic data only.", no_args_is_help=True)


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
