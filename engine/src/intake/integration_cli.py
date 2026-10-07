"""Offline contract exports with atomic, immutable publication."""

import os
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from intake.adapters.contract import canonical_json
from intake.adapters.export import export_run

app = typer.Typer(help="Export synthetic integration evidence offline.", no_args_is_help=True)


class DataKind(StrEnum):
    SYNTHETIC = "synthetic"


def _required(value: str) -> None:
    if not value.strip():
        raise ValueError("an explicit nonempty ID is required")


def _unused(out: Path) -> None:
    if out.exists() or out.is_symlink():
        raise FileExistsError("output already exists")


def _write_new(out: Path, content: str) -> None:
    """Stage complete bytes, then publish without replacing any concurrent winner."""
    _unused(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".integration-", dir=out.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, out)
    finally:
        os.unlink(temporary)


@app.command("export")
def export_command(
    run: Annotated[Path, typer.Option(help="Existing Intake output directory.")],
    agency_id: Annotated[str, typer.Option(help="Explicit synthetic agency ID.")],
    run_id: Annotated[str, typer.Option(help="Expected Intake manifest run ID.")],
    data_kind: Annotated[DataKind, typer.Option(help="Explicit synthetic input attestation.")],
    out: Annotated[Path, typer.Option(help="New canonical packet file; never overwritten.")],
) -> None:
    """Export actual clean records, provenance, and unresolved evidence from a saved run."""
    try:
        _unused(out)
        _required(agency_id)
        _required(run_id)
        packet = export_run(run, agency_id=agency_id, data_kind="synthetic")
        if packet.run_id != run_id:
            raise ValueError("Intake run ID mismatch")
        _write_new(out, canonical_json(packet))
    except (OSError, ValueError):
        typer.echo(
            "Integration export refused: invalid input, run ID, or existing output.", err=True
        )
        raise typer.Exit(2) from None
    typer.echo(f"wrote {out}")
