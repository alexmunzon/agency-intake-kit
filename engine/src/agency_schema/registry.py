"""Rule registry: one place that knows every rule, its severity, and whether it blocks.

Rules register with the @rule decorator. catalog() feeds docs/rules.md and the dashboard
filter list. Tests build their own Registry() so dummy rules never reach the real catalog.
"""

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord, check_rule_identity

RuleFn = Callable[[pl.DataFrame], list[ExceptionRecord]]


@dataclass(frozen=True)
class RuleMeta:
    rule_id: str
    severity: Severity
    family: Family
    description: str
    blocks: bool


class Registry:
    def __init__(self) -> None:
        self._rules: dict[str, tuple[RuleMeta, RuleFn]] = {}

    def rule(
        self,
        rule_id: str,
        severity: Severity,
        family: Family,
        description: str,
        *,
        blocks: bool = False,
    ) -> Callable[[RuleFn], RuleFn]:
        check_rule_identity(rule_id, family, severity, blocks)
        if rule_id in self._rules:
            raise ValueError(f"rule {rule_id} is already registered")
        meta = RuleMeta(rule_id, severity, family, description, blocks)

        def register(fn: RuleFn) -> RuleFn:
            self._rules[rule_id] = (meta, fn)
            return fn

        return register

    def catalog(self) -> list[RuleMeta]:
        return [meta for meta, _ in sorted(self._rules.values(), key=lambda r: r[0].rule_id)]

    def run_rules(self, frame: pl.DataFrame, family: Family | None = None) -> list[ExceptionRecord]:
        """Run every rule (or one family) in rule id order and collect their exceptions."""
        records: list[ExceptionRecord] = []
        for meta in self.catalog():
            if family is not None and meta.family != family:
                continue
            for record in self._rules[meta.rule_id][1](frame):
                if record.rule_id != meta.rule_id or record.severity != meta.severity:
                    raise ValueError(
                        f"rule {meta.rule_id} emitted a record for {record.rule_id} "
                        f"at {record.severity}"
                    )
                records.append(record)
        return records


_default = Registry()
rule = _default.rule
catalog = _default.catalog
run_rules = _default.run_rules
