"""Command line entry point for the synthetic data generator. Commands arrive in later PRs."""

import typer

from synth_agency_data import __version__

app = typer.Typer(help="Synthetic agency data generator.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Keep the app a command group so subcommands arrive cleanly in later PRs."""


@app.command()
def version() -> None:
    """Print the generator version."""
    typer.echo(__version__)
