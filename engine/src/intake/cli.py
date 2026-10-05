"""Command line entry point for the intake pipeline. Commands arrive in later PRs."""

import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from agency_schema import json_schema
from agency_schema.typescript import render_typescript
from intake import __version__
from intake.config import JEV_CHARS_PER_TOKEN
from intake.mapping.jev_mapping import MAPPING_CASSETTES
from jev_client import JevClient

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
    with tempfile.TemporaryDirectory() as tmp:
        fill_drop(drop, Path(tmp), now, Asker(client))
    usage = client.usage
    typer.echo(
        f"Done. Answers {usage.calls}, input tokens {usage.input_tokens}, "
        f"estimated cost ${usage.estimated_cost_usd}"
    )
