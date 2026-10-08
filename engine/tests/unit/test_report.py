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


DEMO = Path(__file__).resolve().parents[3] / "dashboard" / "public" / "demo-run"


def test_status_is_in_words_never_the_code(tmp_path: Path) -> None:
    """#78: an agency owner reads 'Passed with warnings', not PASSED_WITH_WARNINGS."""
    html = render_report(SAMPLE)
    assert "Status: Passed with warnings." in html
    assert 'data-status="PASSED_WITH_WARNINGS"' in html
    assert ">PASSED_WITH_WARNINGS" not in html and "Status: PASSED" not in html


def test_ready_to_sell_count_is_policies_like_the_agents_page() -> None:
    """#76: the demo has 27 RTS-001 policies in 26 cells; the report shows the 27."""
    html = render_report(DEMO)
    assert "Policies sold without ready-to-sell status<b>27</b>" in html
    assert "RTS gaps<b>26</b>" not in html


def test_frozen_clock_run_time_is_not_measured(tmp_path: Path) -> None:
    """#77: a frozen clock pins both times, so 0 seconds would be a fake measurement."""
    assert "Run time: not measured (frozen clock)." in render_report(DEMO)
    run = tmp_path / "run"
    shutil.copytree(SAMPLE, run)
    path = run / "manifest.json"
    path.write_text(path.read_text().replace('"as_of": "2026-10-01T09:00:00Z"', '"as_of": null'))
    html = render_report(run)
    assert "Run time: 47 seconds." in html and "not measured" not in html


def test_report_is_review_handoff_not_go_live_approval() -> None:
    html = render_report(SAMPLE)
    assert "What needs review before handoff?" in html
    assert "Review required before handoff." in html
    assert "not agency go-live approval" in html
    assert "Yes, with fixes" not in html
    assert "This agency can go live" not in html
