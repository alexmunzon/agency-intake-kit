"""A source file's format fingerprint: which headers it has, in which order.

Two exports with the same headers in the same order share a fingerprint, so a saved mapping
is reused only for the export format it was made for (interface section 3).
"""

import hashlib
from collections.abc import Sequence


def format_fingerprint(headers: Sequence[str]) -> str:
    """First 16 hex characters of sha256 over the trimmed, lowercased headers joined by newlines."""
    normalized = "\n".join(header.strip().lower() for header in headers)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
