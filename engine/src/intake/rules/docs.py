"""docs/rules.md, generated from the rule registry."""

import intake.checks  # noqa: F401  (registers the cross-record rules)
import intake.exceptions.pii  # noqa: F401  (registers PII-001)
import intake.rules  # noqa: F401  (registers the row rules)
import intake.rules.catalog  # noqa: F401  (registers ING, MAP, SSN, CMP, TIE)
from agency_schema.registry import catalog

HEADER = """# Rule catalog

Generated from the rule registry by `uv run intake rules --md > ../docs/rules.md`. Do not edit
by hand. All {count} rules; readers, gates, mapping, tie-out, and clean validation raise theirs
outside the registry.

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
    return HEADER.format(count=len(catalog())) + "\n".join(rows) + "\n"
