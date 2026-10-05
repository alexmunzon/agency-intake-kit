"""Every relative link and image in the README and docs points at a file that exists.

Also keeps the house rule: no em dashes in the README, release notes, or ADRs.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "release-notes-v1.0.0.md",
    *sorted((ROOT / "docs" / "adr").glob("*.md")),
]
LINK = re.compile(r"\]\(([^)\s]+)\)")


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_relative_links_resolve(doc: Path) -> None:
    missing = []
    for target in LINK.findall(doc.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.split("#", 1)[0]
        if not (doc.parent / path).exists():
            missing.append(target)
    assert missing == []


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_no_em_dashes(doc: Path) -> None:
    assert chr(0x2014) not in doc.read_text(encoding="utf-8")


def test_demo_gif_under_3_mb() -> None:
    gif = ROOT / "docs" / "screenshots" / "demo.gif"
    assert gif.exists() and gif.stat().st_size < 3_000_000
