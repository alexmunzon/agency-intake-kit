"""Focused link-candidate contract regressions; intentionally independent of SQL views."""

from decimal import Decimal

import pytest
from test_tieout_review_fixes import line, policy, tie


def link_for(result, row: int = 0):
    return result.links[row]


def test_duplicate_member_id_is_ambiguous_and_retains_every_candidate() -> None:
    p1, p2 = policy("P-2"), policy("P-1")  # insertion order opposes lexical order
    p1[3] = p2[3] = "M-DUP"
    link = link_for(tie([p1, p2], [line(1, "DUP", "42.17")]))
    assert link.state == "ambiguous"
    assert link.policy_id is None
    assert {candidate.policy_id for candidate in link.candidates} == {"P-1", "P-2"}
    assert len(link.candidates) == 2
    assert link.amount == Decimal("42.17")
    assert link.lineage.row_number == 4


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_member_ids_never_create_a_strong_match(blank: str | None) -> None:
    p = policy("P-1")
    p[3] = blank
    statement = line(1, None, "26.25")
    statement[3] = blank
    link = link_for(tie([p], [statement]))
    assert link.state == "unmatched"
    assert link.policy_id is None
    assert link.candidates == ()


def test_unique_nonblank_member_id_is_confirmed() -> None:
    link = link_for(tie([policy("P-1")], [line(1, "P-1", "26.25")]))
    assert link.state == "confirmed"
    assert link.policy_id == "P-1"
    assert [candidate.policy_id for candidate in link.candidates] == ["P-1"]


def test_policy_reference_is_carrier_scoped() -> None:
    other = policy("P-OTHER", carrier="Harborline")
    statement = line(1, None, "20.00")
    statement[6] = "P-OTHER"
    link = link_for(tie([other], [statement]))
    assert link.state == "unmatched"
    assert link.policy_id is None
    assert link.candidates == ()


def test_conflicting_strong_keys_are_ambiguous_and_keep_both_candidates() -> None:
    p1, p2 = policy("P-1"), policy("P-2")
    statement = line(1, "P-1", "20.00")
    statement[6] = "P-2"
    link = link_for(tie([p1, p2], [statement]))
    assert link.state == "ambiguous"
    assert link.policy_id is None
    assert {candidate.policy_id for candidate in link.candidates} == {"P-1", "P-2"}


def test_unique_strong_match_survives_compatible_weak_candidates() -> None:
    link = link_for(
        tie(
            [policy("P-1"), policy("P-2")],
            [line(1, "P-1", "20.00", dob="1950-01-02")],
        )
    )
    assert link.state == "confirmed"
    assert link.policy_id == "P-1"
    assert {candidate.policy_id for candidate in link.candidates} == {"P-1", "P-2"}


def test_unmatched_supplied_reference_makes_other_candidate_ambiguous() -> None:
    statement = line(1, "P-1", "20.00")
    statement[6] = "MISSING"
    link = link_for(tie([policy("P-1")], [statement]))
    assert link.state == "ambiguous"
    assert link.policy_id is None
    assert [candidate.policy_id for candidate in link.candidates] == ["P-1"]


def test_same_policy_id_under_two_carriers_keeps_separate_book_rows() -> None:
    policies = [
        policy("P-SHARED", carrier="Bluepeak", status="CANCELLED"),
        policy("P-SHARED", carrier="Harborline", status="ACTIVE"),
    ]
    statements = [
        line(1, "P-SHARED", "26.25", carrier="Bluepeak"),
        line(2, "P-SHARED", "26.25", carrier="Harborline"),
    ]
    result = tie(policies, statements)
    bluepeak, harborline = result.links
    assert (bluepeak.state, bluepeak.policy_id) == ("confirmed", "P-SHARED")
    assert (harborline.state, harborline.policy_id) == ("confirmed", "P-SHARED")
    assert bluepeak.candidates[0].lineage.row_number == 2
    assert harborline.candidates[0].lineage.row_number == 3
    conflicts = [v for v in result.variances.variances if v.rule_id == "TIE-004"]
    assert [(v.carrier, v.policy_id) for v in conflicts] == [("Bluepeak", "P-SHARED")]
