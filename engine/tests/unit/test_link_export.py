import json
from decimal import Decimal

from test_tieout_review_fixes import LINE, POLICY, line, policy, reader_frame, tie

from agency_schema.lineage import Lineage
from intake.tieout.link_evidence import LinkEvidence
from intake.tieout.variances import write_tieout


def test_link_export_preserves_statement_and_candidate_lineage(tmp_path):
    result = tie(
        [policy("P1")],
        [line(1, "P1", "-26.25", kind="CHARGEBACK")],
    )
    links = result.links
    assert len(links) == 1
    link = links[0]
    assert link.amount == Decimal("-26.25")
    statement_line = Lineage.model_validate(
        reader_frame(
            LINE, [line(1, "P1", "-26.25", kind="CHARGEBACK")], "bluepeak.xlsx", "Statement", 4
        )["lineage"][0]
    )
    policy_line = Lineage.model_validate(
        reader_frame(POLICY, [policy("P1")], "crm.csv")["lineage"][0]
    )
    assert link.lineage == statement_line
    assert link.candidates[0].lineage == policy_line

    write_tieout(result, tmp_path)
    path = tmp_path / "tie_out" / "links.jsonl"
    exported = path.read_text(encoding="utf-8").splitlines()
    assert len(exported) == 1
    restored = LinkEvidence.model_validate_json(exported[0])
    assert restored.lineage == link.lineage
    assert restored.candidates[0].lineage == link.candidates[0].lineage
    assert restored.amount == Decimal("-26.25")
    assert json.loads(exported[0])["amount"] == "-26.25"
