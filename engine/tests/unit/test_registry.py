from typing import Any

import polars as pl
import pytest

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.registry import Registry, RuleMeta


@pytest.fixture
def registry() -> Registry:
    # A throwaway registry, so test rules never leak into the real catalog.
    return Registry()


def test_registers_a_dummy_rule_and_lists_it(registry: Registry) -> None:
    @registry.rule("DOB-001", Severity.ERROR, Family.DOB, "DOB unparseable")
    def dummy(frame: pl.DataFrame) -> list[ExceptionRecord]:
        return []

    assert registry.catalog() == [
        RuleMeta(
            rule_id="DOB-001",
            severity=Severity.ERROR,
            family=Family.DOB,
            description="DOB unparseable",
            blocks=False,
        )
    ]
    assert dummy(pl.DataFrame()) == []  # the decorator returns the function unchanged


def test_catalog_is_sorted_by_rule_id(registry: Registry) -> None:
    for rule_id in ["DOB-002", "ADR-001", "DOB-001"]:
        registry.rule(rule_id, Severity.ERROR, Family(rule_id[:3]), "x")(lambda f: [])
    assert [m.rule_id for m in registry.catalog()] == ["ADR-001", "DOB-001", "DOB-002"]


def test_duplicate_rule_id_is_refused(registry: Registry) -> None:
    registry.rule("DOB-001", Severity.ERROR, Family.DOB, "x")(lambda f: [])
    with pytest.raises(ValueError, match="already registered"):
        registry.rule("DOB-001", Severity.ERROR, Family.DOB, "x")


def test_rule_id_must_match_family(registry: Registry) -> None:
    with pytest.raises(ValueError, match="family"):
        registry.rule("DOB-001", Severity.ERROR, Family.MBI, "x")


def test_rule_id_format(registry: Registry) -> None:
    with pytest.raises(ValueError, match="rule id"):
        registry.rule("DOB1", Severity.ERROR, Family.DOB, "x")


def test_only_the_three_blockers_may_block(registry: Registry) -> None:
    with pytest.raises(ValueError, match="blocker"):
        registry.rule("DOB-001", Severity.BLOCKER, Family.DOB, "x", blocks=True)
    with pytest.raises(ValueError, match="blocks"):
        registry.rule("CMP-001", Severity.BLOCKER, Family.CMP, "x", blocks=False)
    registry.rule("CMP-001", Severity.BLOCKER, Family.CMP, "x", blocks=True)(lambda f: [])


def test_run_rules_filters_by_family(registry: Registry, exception_kwargs: dict[str, Any]) -> None:
    record = ExceptionRecord(**exception_kwargs)
    registry.rule("DOB-001", Severity.ERROR, Family.DOB, "x")(lambda f: [record])
    registry.rule("ADR-001", Severity.ERROR, Family.ADR, "x")(lambda f: [])
    frame = pl.DataFrame({"dob": ["bad"]})
    assert registry.run_rules(frame) == [record]
    assert registry.run_rules(frame, family=Family.DOB) == [record]
    assert registry.run_rules(frame, family=Family.ADR) == []


def test_run_rules_refuses_a_record_for_another_rule(
    registry: Registry, exception_kwargs: dict[str, Any]
) -> None:
    record = ExceptionRecord(**exception_kwargs)  # DOB-001
    registry.rule("DOB-002", Severity.ERROR, Family.DOB, "x")(lambda f: [record])
    with pytest.raises(ValueError, match="DOB-002"):
        registry.run_rules(pl.DataFrame())
