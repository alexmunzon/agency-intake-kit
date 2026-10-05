"""report.html escapes everything it shows: a value from the drop can never become markup."""

import json
import shutil
from pathlib import Path

from intake.report.html import money, render_report

SAMPLE = Path(__file__).resolve().parents[3] / "fixtures" / "sample-run"


def test_messages_are_escaped(tmp_path: Path) -> None:
    run = tmp_path / "run"
    shutil.copytree(SAMPLE, run)
    path = run / "exceptions.jsonl"
    lines = path.read_text().splitlines()
    first = json.loads(lines[0])
    first["message"] = "<b>bold</b> & <script>alert(1)</script>"
    path.write_text("\n".join([json.dumps(first), *lines[1:]]) + "\n")
    html = render_report(run)
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; &lt;script&gt;" in html
    assert "<script" not in html and "<b>bold" not in html


def test_money_is_exact_text() -> None:
    assert money("-1234.5") == "-$1,234.50"
    assert money("0.10") == "$0.10"
    assert money(None) == "Not checked"
