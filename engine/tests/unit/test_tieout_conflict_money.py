from decimal import Decimal

from test_tieout_review_fixes import LINE, POLICY, line, policy, reader_frame

from intake.tieout import run_tieout


def test_conflicting_candidate_and_unmatched_amounts_conserve_carrier_total() -> None:
    p1, p2 = policy("P1"), policy("P2")
    p2[1] = "C2"
    conflicting = line(1, "P1", "20.00", dob="1952-02-03")
    conflicting[4] = "Ben Kay"
    unmatched = line(2, None, "-3.00")
    result = run_tieout(
        {
            "policies": reader_frame(POLICY, [p1, p2], "crm.csv"),
            "commission_lines": reader_frame(
                LINE, [conflicting, unmatched], "bluepeak.xlsx", "Statement", 4
            ),
            "clients": reader_frame(
                "client_id first_name last_name dob",
                [["C-1", "Ann", "Lee", "1950-01-02"], ["C2", "Ben", "Kay", "1952-02-03"]],
                "crm_clients.csv",
            ),
        },
        run_id="run-7",
        rates={("MA", "RENEWAL"): Decimal("26.25")},
    )

    ambiguous, orphan = sorted(result.links, key=lambda link: link.lineage.row_number)
    assert (ambiguous.state, ambiguous.policy_id, ambiguous.amount) == (
        "ambiguous",
        None,
        Decimal("20.00"),
    )
    assert {candidate.policy_id for candidate in ambiguous.candidates} == {"P1", "P2"}
    assert (orphan.state, orphan.policy_id, orphan.amount) == ("unmatched", None, Decimal("-3.00"))
    carrier = next(row for row in result.totals_by_carrier.rows if row.key == "Bluepeak")
    signed = sum((link.amount for link in result.links if link.amount is not None), Decimal("0.00"))
    assert signed == carrier.statement_paid == carrier.unexplained_revenue == Decimal("17.00")
    assert not [v for v in result.variances.variances if v.rule_id in {"TIE-003", "TIE-004"}]
