"""Scoped readiness commands. Shared intake CLI registration belongs to Session 7."""

import json
from pathlib import Path
from typing import Annotated

import typer

from intake.source_readiness import evaluate, import_package, parse_package

app = typer.Typer(
    help="Inspect and save synthetic source readiness snapshots. No approval authority."
)


@app.command("check")
def check(source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Recompute coverage at the package's explicit evaluation clock."""
    try:
        result = evaluate(parse_package(source.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        raise typer.BadParameter("Invalid readiness package; no state changed.") from None
    typer.echo(result.model_dump_json(indent=2))


@app.command("import")
def import_snapshot(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    out: Annotated[
        Path, typer.Option(help="Local disk snapshot, atomically replaced after validation.")
    ],
) -> None:
    """Save a full snapshot locally. A malformed import leaves the previous file intact."""
    try:
        import_package(source.read_text(encoding="utf-8"), out)
    except (ValueError, OSError):
        raise typer.BadParameter("Import failed; previous snapshot preserved.") from None
    typer.echo("Saved local disk snapshot. No hosted persistence or approval.")


@app.command("export")
def export_onboarding(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    out: Annotated[
        Path, typer.Option(help="New reusable onboarding ZIP; existing output refused.")
    ],
) -> None:
    """Carry original evidence and all receipt/correction history into onboarding."""
    from intake.source_readiness_export import export_package

    try:
        export_package(parse_package(source.read_text(encoding="utf-8")), out)
    except (ValueError, OSError):
        raise typer.BadParameter(
            "Export refused; choose a new output and a valid package."
        ) from None
    typer.echo(json.dumps({"export": str(out), "review_state": "not_reviewed"}))


if __name__ == "__main__":
    app()
