import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

import agency_schema
from agency_schema.lineage import Lineage
from agency_schema.models import TABLE_MODELS, Client, Household, Policy, Rts


@pytest.fixture
def policy_kwargs(lineage_kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_id": "P-00417",
        "client_id": "C-00001",
        "carrier": "Harborline",
        "plan_id": "H1234-001",
        "line_of_business": "MA",
        "state": "TX",
        "eligibility_reason": "AGE",
        "effective_date": date(2026, 1, 1),
        "termination_date": None,
        "status": "ACTIVE",
        "writing_agent_npn": "1884412",
        "monthly_premium": Decimal("0.00"),
        "carrier_member_id": "HL-998213",
        "lineage": lineage_kwargs,
    }


def test_six_tables_with_spec_names() -> None:
    assert set(TABLE_MODELS) == {
        "clients",
        "households",
        "agents",
        "rts",
        "policies",
        "commission_lines",
    }


@pytest.mark.parametrize("table", sorted(TABLE_MODELS))
def test_every_table_requires_lineage(table: str) -> None:
    field = TABLE_MODELS[table].model_fields["lineage"]
    assert field.annotation is Lineage
    assert field.is_required()


@pytest.mark.parametrize("table", sorted(TABLE_MODELS))
def test_no_field_has_a_default(table: str) -> None:
    # A default would let a forgotten column turn into a silent blank.
    defaults = [n for n, f in TABLE_MODELS[table].model_fields.items() if not f.is_required()]
    assert defaults == []


def test_omitting_a_nullable_field_is_an_error(policy_kwargs: dict[str, Any]) -> None:
    del policy_kwargs["termination_date"]
    with pytest.raises(ValidationError, match="termination_date"):
        Policy(**policy_kwargs)


def test_extra_fields_are_rejected(policy_kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="extra"):
        Policy(**policy_kwargs, ssn="000000000")


def test_line_of_business_is_closed(policy_kwargs: dict[str, Any]) -> None:
    policy_kwargs["line_of_business"] = "MAPD"
    with pytest.raises(ValidationError):
        Policy(**policy_kwargs)


def test_carrier_is_an_open_string(policy_kwargs: dict[str, Any]) -> None:
    policy_kwargs["carrier"] = "Some Carrier Nobody Listed"
    assert Policy(**policy_kwargs).carrier == "Some Carrier Nobody Listed"


def test_money_is_exact_decimal(policy_kwargs: dict[str, Any]) -> None:
    policy_kwargs["monthly_premium"] = "0.10"
    premium = Policy(**policy_kwargs).monthly_premium
    assert isinstance(premium, Decimal)
    assert premium + Decimal("0.20") == Decimal("0.30")


def test_money_rejects_fractions_of_a_cent(policy_kwargs: dict[str, Any]) -> None:
    policy_kwargs["monthly_premium"] = "61.055"
    with pytest.raises(ValidationError):
        Policy(**policy_kwargs)


def test_blank_string_is_not_a_second_kind_of_missing(policy_kwargs: dict[str, Any]) -> None:
    policy_kwargs["state"] = ""  # must be None so the client-state fallback fires
    with pytest.raises(ValidationError):
        Policy(**policy_kwargs)


@pytest.mark.parametrize(("field", "value"), [("appointed", "yes"), ("plan_year", "2026")])
def test_no_silent_coercion_from_strings(
    lineage_kwargs: dict[str, Any], field: str, value: str
) -> None:
    kwargs: dict[str, Any] = {
        "npn": "1884412",
        "carrier": "Harborline",
        "state": "TX",
        "plan_year": 2026,
        "line_of_business": "MA",
        "appointed": True,
        "certified": True,
        "effective_date": date(2026, 1, 1),
        "end_date": None,
        "lineage": lineage_kwargs,
    }
    assert Rts(**kwargs).plan_year == 2026
    kwargs[field] = value
    with pytest.raises(ValidationError):
        Rts(**kwargs)


def test_list_fields_cannot_change_after_validation(lineage_kwargs: dict[str, Any]) -> None:
    household = Household(
        household_id="H-1", primary_client_id="C-1", members=["C-1"], lineage=lineage_kwargs
    )
    assert household.members == ("C-1",)


def test_lineage_row_number_starts_at_one(lineage_kwargs: dict[str, Any]) -> None:
    lineage_kwargs["row_number"] = 0
    with pytest.raises(ValidationError):
        Lineage(**lineage_kwargs)


def test_lineage_raw_hash_is_sha256_hex(lineage_kwargs: dict[str, Any]) -> None:
    lineage_kwargs["raw_hash"] = "not-a-hash"
    with pytest.raises(ValidationError):
        Lineage(**lineage_kwargs)


def test_client_mbi_may_be_empty_but_must_be_given(lineage_kwargs: dict[str, Any]) -> None:
    client = Client(
        client_id="C-00001",
        first_name="Ana",
        last_name="De La Cruz",
        dob=date(1958, 3, 12),
        phone=None,
        email=None,
        address_line1="1 Main St",
        city="Austin",
        state="TX",
        zip="78701",
        mbi=None,
        household_id=None,
        notes=None,
        lineage=lineage_kwargs,
    )
    assert client.mbi is None


def test_json_schema_covers_every_model() -> None:
    schema = agency_schema.json_schema()
    json.dumps(schema)  # must be plain JSON
    defs = schema["$defs"]
    for model in [*TABLE_MODELS.values(), Lineage, agency_schema.ExceptionRecord]:
        assert model.__name__ in defs
    for model in TABLE_MODELS.values():
        assert "lineage" in defs[model.__name__]["required"]


def test_json_schema_is_stable() -> None:
    assert agency_schema.json_schema() == agency_schema.json_schema()


def test_nothing_is_named_exception() -> None:
    for module in ("enums", "lineage", "models", "exceptions", "registry"):
        mod = __import__(f"agency_schema.{module}", fromlist=["_"])
        assert getattr(mod, "Exception", Exception) is Exception
