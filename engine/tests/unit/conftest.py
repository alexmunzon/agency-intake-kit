from typing import Any

import pytest

RAW_HASH = "a" * 64


@pytest.fixture
def lineage_kwargs() -> dict[str, Any]:
    return {
        "source_file": "crm_export.csv",
        "sheet": None,
        "row_number": 2,
        "raw_hash": RAW_HASH,
        "run_id": "test-run",
        "mapping_version": "v1",
    }


@pytest.fixture
def exception_kwargs(lineage_kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "EX-000001",
        "rule_id": "DOB-001",
        "severity": "ERROR",
        "family": "DOB",
        "source": "crm",
        "row_number": 2,
        "raw_hash": RAW_HASH,
        "field": "dob",
        "value_minimized": "19**-**-**",
        "message": "The date of birth is not a date",
        "suggested_fix": "Correct the date",
        "blocks_load": False,
        "lane": "UNREVIEWED",
        "jev": None,
        "lineage": lineage_kwargs,
    }
