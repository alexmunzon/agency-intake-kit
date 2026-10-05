"""Read a delimited text file into a raw frame. Values stay exactly as read."""

from pathlib import Path

from intake.readers import RawTable, table_from_rows
from intake.readers.sniff import decode, sniff_delimiter, split_rows


def read_csv(path: Path, *, source: str, run_id: str, mapping_version: str) -> RawTable:
    text, encoding = decode(path.read_bytes())
    guess = sniff_delimiter(text)
    return table_from_rows(
        split_rows(text, guess.delimiter),
        source=source,
        source_file=path.name,
        sheet=None,
        run_id=run_id,
        mapping_version=mapping_version,
        encoding=encoding,
        delimiter=guess.delimiter,
        delimiter_confident=guess.confident,
    )
