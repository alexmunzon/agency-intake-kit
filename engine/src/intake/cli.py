"""Command line entry point for the intake pipeline. Commands arrive in later PRs."""

import typer

from intake import __version__

app = typer.Typer(help="Agency intake pipeline. Synthetic data only.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Keep the app a command group so subcommands arrive cleanly in later PRs."""


@app.command()
def version() -> None:
    """Print the engine version."""
    typer.echo(__version__)
