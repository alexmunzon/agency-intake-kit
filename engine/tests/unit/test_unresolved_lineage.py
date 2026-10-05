import json

import pytest
from pydantic import ValidationError

from agency_schema.lineage import Lineage
from intake.run.unresolved_evidence import UnresolvedEvidence, serialize_unresolved_evidence


def test_sheet_lineage_roundtrip_is_exact_and_export_is_stable():
    rows = [
        UnresolvedEvidence(
            run_id="r1",
            source="crm",
            reason="dob_blank",
            lineage=Lineage(
                source_file="crm.xlsx",
                sheet=sheet,
                row_number=7,
                raw_hash="a" * 64,
                run_id="r1",
                mapping_version="map-v1",
            ),
        )
        for sheet in ("Roster A", "Roster B")
    ]
    left = serialize_unresolved_evidence(rows, "r1")
    assert left == serialize_unresolved_evidence(list(reversed(rows)), "r1")
    parsed = [UnresolvedEvidence.model_validate_json(line) for line in left.splitlines()]
    assert [case.lineage for case in parsed] == [case.lineage for case in rows]
    assert [json.loads(line)["lineage"]["raw_hash"] for line in left.splitlines()] == [
        "a" * 64,
        "a" * 64,
    ]
    assert [case.lineage.sheet for case in parsed] == ["Roster A", "Roster B"]
    with pytest.raises(ValidationError, match="lineage run_id"):
        UnresolvedEvidence(
            run_id="r1",
            source="crm",
            reason="dob_blank",
            lineage=Lineage(
                source_file="crm.xlsx",
                sheet="Roster A",
                row_number=7,
                raw_hash="a" * 64,
                run_id="r2",
                mapping_version="map-v1",
            ),
        )
    with pytest.raises(ValueError, match="duplicate"):
        serialize_unresolved_evidence((rows[0], rows[0]), "r1")
