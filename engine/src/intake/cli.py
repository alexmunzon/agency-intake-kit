"""Command line entry point for the intake pipeline. Commands arrive in later PRs."""

import json
from pathlib import Path
from typing import Annotated

import typer

from agency_schema import json_schema
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
