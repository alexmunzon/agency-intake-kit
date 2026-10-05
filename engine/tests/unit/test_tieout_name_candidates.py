"""Name/DOB links stay provisional or ambiguous and never choose a policy."""

from decimal import Decimal

from test_tieout_review_fixes import line, policy, tie


def test_unique_name_dob_is_provisional_without_policy_attribution() -> None:
    result = tie([policy("P1")], [line(1, None, "26.25", dob="1950-01-02")])
    link = result.links[0]
    assert link.state == "provisional"
    assert link.policy_id is None
    assert [(c.policy_id, c.methods) for c in link.candidates] == [("P1", ("NAME_DOB",))]
    assert link.amount == Decimal("26.25")
    assert result.totals_by_carrier.rows[0].statement_paid == Decimal("26.25")


def test_shared_name_dob_is_ambiguous_and_conserves_signed_amount_once() -> None:
    statements = [line(1, None, "26.25", dob="1950-01-02"), line(2, None, "-5.00")]
    first = tie([policy("P2"), policy("P1")], statements)
    second = tie([policy("P1"), policy("P2")], statements)
    link, unmatched = first.links
    assert link.state == "ambiguous" and link.policy_id is None
    assert [(c.policy_id, c.methods) for c in link.candidates] == [
        ("P1", ("NAME_DOB",)),
        ("P2", ("NAME_DOB",)),
    ]
    assert [(c.policy_id, c.methods) for c in second.links[0].candidates] == [
        ("P1", ("NAME_DOB",)),
        ("P2", ("NAME_DOB",)),
    ]
    assert unmatched.state == "unmatched" and unmatched.policy_id is None
    assert [entry.amount for entry in first.links] == [Decimal("26.25"), Decimal("-5.00")]
    assert sum((entry.amount or Decimal("0.00") for entry in first.links), Decimal("0.00")) == (
        Decimal("21.25")
    )
    assert first.totals_by_carrier.rows[0].statement_paid == Decimal("21.25")
