"""Command line entry point for the synthetic data generator."""

from pathlib import Path
from typing import Annotated

import typer

from synth_agency_data import __version__
from synth_agency_data.canonical_writer import write_world
from synth_agency_data.injectors import Defect, inject
from synth_agency_data.world import build_world

app = typer.Typer(help="Synthetic agency data generator.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Keep the app a command group."""


@app.command()
def version() -> None:
    """Print the generator version."""
    typer.echo(__version__)


@app.command()
def generate(
    out: Annotated[Path, typer.Option(help="Output folder, for example ../fixtures/agency-a.")],
    seed: Annotated[
        int, typer.Option(help="Random seed. The same seed gives identical files.")
    ] = 42,
    clients: Annotated[int, typer.Option(help="Number of clients.")] = 2000,
    inject_defects: Annotated[
        bool,
        typer.Option(
            "--inject/--no-inject",
            help="Plant SPEC examples 3 and 4 and inject labeled defects (needs seed 42). "
            "--no-inject writes the clean world to canonical/ instead.",
        ),
    ] = True,
) -> None:
    """Write canonical CSVs plus ground_truth.json, defected by default."""
    world = build_world(seed=seed, n_clients=clients)
    defects: list[Defect] = []
    folder = "canonical"
    if inject_defects:
        try:
            world, defects = inject(world)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
        folder = "canonical-defected"
    write_world(world, out, defects, folder)
    counts = ", ".join(f"{len(rows)} {name}" for name, rows in world.tables.items())
    typer.echo(f"Wrote {out / folder}: {counts}, {len(defects)} defects")
