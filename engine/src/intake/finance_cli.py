"""Scoped finance CLI. Shared registration is owned by Session 7.

Run directly with python -m intake.finance_cli until shared registration lands.
"""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer

from intake.finance_adapter import StatementAdapter, import_statement
from intake.finance_store import ReceiptStore
from intake.revenue import RevenueMapping
from intake.revenue_ledger import ReceiptBatch

app = typer.Typer(help="Local synthetic receipt storage and neutral finance exports.")


def _publish_new(output: Path, content: str) -> None:
    """Stage complete bytes, then publish without replacing a concurrent writer."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        raise FileExistsError("output already exists")
    fd, temporary = tempfile.mkstemp(prefix=".finance-", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
        directory = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _refusal() -> Iterator[None]:
    try:
        yield
    except Exception:
        typer.echo(
            "Finance operation refused. Check inputs, IDs, store integrity and output paths.",
            err=True,
        )
        raise typer.Exit(1) from None


@app.command("init")
def initialize(store: Path, mapping: Path) -> None:
    """Create a new local store with a pinned mapping snapshot."""
    with _refusal():
        ReceiptStore.create(store, RevenueMapping.model_validate_json(mapping.read_bytes()))


@app.command("import-statement")
def adapt(source: Path, config: Path, output: Path) -> None:
    """Convert an explicit CSV/XLSX layout to an immutable statement package."""
    with _refusal():
        package = import_statement(
            source, StatementAdapter.model_validate_json(config.read_bytes())
        )
        _publish_new(output, package.model_dump_json(indent=2) + "\n")


@app.command("append")
def append(store: Path, operation_id: str, batch: Path) -> None:
    """Atomically append a receipt batch. Exact retries return the original outcome."""
    with _refusal():
        result = ReceiptStore(store).append(
            operation_id, ReceiptBatch.model_validate_json(batch.read_bytes())
        )
        typer.echo(result.model_dump_json(indent=2))


@app.command("export")
def export(store: Path, output: Path) -> None:
    """Export the existing neutral ledger JSON; never overwrite a prior export."""
    with _refusal():
        result = ReceiptStore(store).read()
        _publish_new(output, result.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    app()
