"""docs/rules.md, generated from the rule registry."""

import intake.exceptions.pii  # noqa: F401  (registers PII-001)
import intake.rules  # noqa: F401  (registers the row rules)
from agency_schema.registry import catalog

HEADER = """# Rule catalog

Generated from the rule registry by `uv run intake rules --md > ../docs/rules.md`. Do not edit
by hand. Rules appear here as their PRs land; the full planned list is BUILD-GUIDE section 6.

Severity decides what happens to a row: a blocker stops the run, an error keeps the row out of
the load file, a warning passes with a flag, and info is only logged.

| Rule | Severity | Family | Blocks the run | What it checks |
|---|---|---|---|---|
"""


def render_rules_md() -> str:
    rows = [
        f"| {m.rule_id} | {m.severity.title()} | {m.family} | {'yes' if m.blocks else 'no'} | "
        f"{m.description} |"
        for m in catalog()
    ]
    return HEADER + "\n".join(rows) + "\n"
