"""Recorded answers, keyed by a hash of the exact request body.

Recipe (PR 7, 11, and 12 depend on it): serialize the request body as JSON with sorted keys,
separators (",", ":"), and non-ASCII kept as is, encode as UTF-8, and take the SHA-256 hex
digest. The cassette is tests/cassettes/<hash>.json holding {"request", "response"} only.
Headers are never stored, so the API key cannot end up in a cassette.
"""

import hashlib
import json
from pathlib import Path
from typing import Any


class CassetteMiss(LookupError):
    """Replay mode found no recording for this request."""

    def __init__(self, request_hash: str, cassette_dir: Path) -> None:
        self.request_hash = request_hash
        super().__init__(
            f"No Jev cassette for request {request_hash} in {cassette_dir}. "
            "Record it with JEV_MODE=record after Alex approves the spend."
        )


def canonical_json(body: Any) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_hash(body: Any) -> str:
    """Public on purpose: PR 11 deduplicates identical requests with the same hash."""
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def cassette_path(cassette_dir: Path, body: Any) -> Path:
    return cassette_dir / f"{request_hash(body)}.json"


def load_cassette(cassette_dir: Path, body: Any) -> dict[str, Any] | None:
    path = cassette_path(cassette_dir, body)
    if not path.exists():
        return None
    response: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))["response"]
    return response


def save_cassette(cassette_dir: Path, body: Any, response: dict[str, Any]) -> Path:
    cassette_dir.mkdir(parents=True, exist_ok=True)
    path = cassette_path(cassette_dir, body)
    text = json.dumps({"request": body, "response": response}, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
    return path
