"""Command line entry point for the synthetic data generator."""

from pathlib import Path
from typing import Annotated

import typer

from synth_agency_data import __version__
from synth_agency_data.canonical_writer import write_world
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
) -> None:
    """Write the clean world as canonical CSVs plus an empty ground_truth.json."""
    world = build_world(seed=seed, n_clients=clients)
    write_world(world, out)
    counts = ", ".join(f"{len(rows)} {name}" for name, rows in world.tables.items())
    typer.echo(f"Wrote {out / 'canonical'}: {counts}")
