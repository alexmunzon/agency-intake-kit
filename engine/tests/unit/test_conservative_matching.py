from decimal import Decimal

import pytest
from test_tieout_review_fixes import line, policy, tie


@pytest.mark.parametrize("case", ["duplicate", "conflicting", "missing", "weak", "compatible"])
def test_only_consistent_strong_keys_attribute_policy(case):
    policies = [policy("P1"), policy("P2")]
    statement = line(1, "P1", "20.00")
    if case == "duplicate":
        policies[1][3] = policies[0][3]
    elif case in {"conflicting", "missing"}:
        statement[6] = "P2" if case == "conflicting" else "MISSING"
    elif case == "weak":
        statement = line(1, None, "20.00", dob="1950-01-02")
    else:
        statement = line(1, "P1", "20.00", dob="1950-01-02")
    result = tie(policies, [statement])
    assert result.legs[1].matched == int(case == "compatible")
    unresolved = [v for v in result.variances.variances if v.rule_id == "TIE-002"]
    assert len(unresolved) == int(case != "compatible")
    assert all(v.policy_id is None for v in unresolved)
    assert all("unresolved" in e.message for e in result.exceptions if e.rule_id == "TIE-002")
    assert result.totals_by_carrier.rows[0].statement_paid == Decimal("20.00")


def test_same_policy_id_remains_separate_across_carriers():
    result = tie(
        [policy("P1", status="CANCELLED"), policy("P1", carrier="Harborline")],
        [line(1, "P1", "26.25"), line(2, "P1", "26.25", carrier="Harborline")],
    )
    assert result.legs[1].matched == 2
    conflicts = [v for v in result.variances.variances if v.rule_id == "TIE-004"]
    assert [(v.carrier, v.policy_id) for v in conflicts] == [("Bluepeak", "P1")]
