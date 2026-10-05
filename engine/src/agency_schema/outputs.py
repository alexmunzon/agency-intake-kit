"""Run outputs: the files in runs/<run_id>/ that the dashboard and report read.

Same ground rules as the tables: no defaults, unknown fields refused, blank means None.
A count that was never measured (a tie-out leg that did not run) is None, never 0, so a
missing check cannot look like a clean one. Money is written to JSON as text ("61.05").
"""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, model_validator

from agency_schema.exceptions import Probability
from agency_schema.lineage import NonEmpty, OptionalText, RowNumber, Sha256, StrictModel
from agency_schema.models import Money

Count = Annotated[StrictInt, Field(ge=0)]
UnsignedMoney = Annotated[Decimal, Field(max_digits=12, decimal_places=2, ge=0)]
# Jev costs fractions of a cent per run, so cents would round every run to $0.00.
UsdCost = Annotated[Decimal, Field(max_digits=12, decimal_places=6, ge=0)]
Period = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]  # YYYY-MM


class RunStatus(StrEnum):
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"


class LegStatus(StrEnum):
    RAN = "RAN"
    NOT_RUN = "NOT_RUN"  # a source was missing or a blocker stopped the run


class TieOutLeg(StrEnum):
    BOOK_VS_STATEMENT = "BOOK_VS_STATEMENT"  # leg A, TIE-001
    STATEMENT_VS_BOOK = "STATEMENT_VS_BOOK"  # leg B, TIE-002
    CRM_VS_STATEMENT = "CRM_VS_STATEMENT"  # leg C, TIE-004

    @classmethod
    def file_stems(cls) -> list[str]:
        """leg_<stem>.json names in tie_out/, in leg order."""
        return [leg.value.lower() for leg in cls]


class RtsCellState(StrEnum):
    HELD_AND_USED = "HELD_AND_USED"
    HELD_UNUSED = "HELD_UNUSED"
    USED_WITHOUT_RTS = "USED_WITHOUT_RTS"  # an RTS-001 gap


class JevMode(StrEnum):
    REPLAY = "replay"
    OFF = "off"
    LIVE = "live"
    RECORD = "record"


class InputFile(StrictModel):
    source: NonEmpty  # crm, enrollment, statement_<carrier>, roster
    file_name: NonEmpty
    sha256: Sha256
    rows_expected: Count | None  # from drop/manifest.json or the file's total row
    rows_received: Count


class JevUsage(StrictModel):
    mode: JevMode
    calls: Count
    input_tokens: Count
    output_tokens: Count
    estimated_cost_usd: UsdCost

    @model_validator(mode="after")
    def _off_means_no_calls(self) -> Self:
        if self.mode == JevMode.OFF and (self.calls or self.input_tokens or self.output_tokens):
            raise ValueError("Jev mode off makes no calls")
        return self


class Manifest(StrictModel):
    run_id: NonEmpty
    started_at: AwareDatetime
    finished_at: AwareDatetime
    as_of: AwareDatetime | None  # the frozen clock (--as-of) when given, else None
    engine_version: NonEmpty
    status: RunStatus
    status_reason: OptionalText  # one plain sentence for the banner; None only when PASSED
    inputs: tuple[InputFile, ...]
    jev: JevUsage
    # The $0.50 spend cap was reached: Jev went off for the rest of the run (SPEC "Spend cap").
    # jev.mode stays the configured mode; calls and tokens are what was actually used.
    budget_tripped: StrictBool
    thresholds: dict[NonEmpty, float]  # config.py values used by this run

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at is before started_at")
        if (self.status_reason is None) != (self.status == RunStatus.PASSED):
            raise ValueError("status_reason is required exactly when the run did not fully pass")
        return self


class SeverityCounts(StrictModel):
    blocker: Count
    error: Count
    warning: Count
    info: Count


class LegSummary(StrictModel):
    leg: TieOutLeg
    status: LegStatus
    not_run_reason: OptionalText
    matched: Count | None
    unmatched: Count | None
    weak_matched: Count | None  # the part of matched made on name plus DOB only, TIE-006
    variance_count: Count | None
    variance_dollars: UnsignedMoney | None  # sum of absolute differences

    @model_validator(mode="after")
    def _ran_or_not(self) -> Self:
        counts = (self.matched, self.unmatched, self.weak_matched, self.variance_count)
        measured = [*counts, self.variance_dollars]
        if self.status == LegStatus.RAN:
            if any(v is None for v in measured) or self.not_run_reason is not None:
                raise ValueError("a leg that ran needs every count and no not_run_reason")
            if (self.weak_matched or 0) > (self.matched or 0):
                raise ValueError("weak_matched is part of matched, so it cannot exceed it")
        elif any(v is not None for v in measured) or self.not_run_reason is None:
            raise ValueError("a leg that did not run has no counts and needs not_run_reason")
        return self


# Each variance rule belongs to one leg, or to no leg for the dollar checks.
RULE_LEG = {
    "TIE-001": TieOutLeg.BOOK_VS_STATEMENT,
    "TIE-002": TieOutLeg.STATEMENT_VS_BOOK,
    "TIE-004": TieOutLeg.CRM_VS_STATEMENT,
    "TIE-003": None,
    "TIE-005": None,
}


class Variance(StrictModel):
    """One tie-out finding. Its ExceptionRecord in exceptions.jsonl has the same exception_id."""

    rule_id: Literal["TIE-001", "TIE-002", "TIE-003", "TIE-004", "TIE-005"]
    exception_id: NonEmpty
    leg: TieOutLeg | None  # None for dollar checks (TIE-003, TIE-005)
    carrier: OptionalText
    statement_period: Period | None
    line_no: RowNumber | None
    policy_id: OptionalText
    carrier_member_id: OptionalText
    agent_npn: OptionalText
    paid: Money | None
    expected: Money | None
    difference: Money  # paid minus expected, a missing side counting as zero

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.difference != (self.paid or 0) - (self.expected or 0):
            raise ValueError("difference must equal paid minus expected")
        if self.leg != RULE_LEG[self.rule_id]:
            raise ValueError(f"{self.rule_id} belongs to leg {RULE_LEG[self.rule_id]}")
        return self


class LegResult(LegSummary):
    """tie_out/leg_<stem>.json: the leg's summary plus its own variances."""

    variances: tuple[Variance, ...]

    @model_validator(mode="after")
    def _adds_up(self) -> Self:
        if any(v.leg != self.leg for v in self.variances):
            raise ValueError("every variance must belong to this leg")
        if self.status == LegStatus.NOT_RUN:
            if self.variances:
                raise ValueError("a leg that did not run has no variances")
        elif self.variance_count != len(self.variances) or self.variance_dollars != sum(
            abs(v.difference) for v in self.variances
        ):
            raise ValueError("variance_count and variance_dollars must match the variances")
        return self


class VarianceReport(StrictModel):
    """tie_out/variances.json: every variance from every leg and dollar check."""

    variances: tuple[Variance, ...]


class TotalRow(StrictModel):
    key: NonEmpty  # the carrier name or the agent NPN
    book_expected: Money
    statement_paid: Money
    difference: Money  # statement_paid minus book_expected
    unexplained_revenue: Money  # orphan payments (TIE-002) inside statement_paid
    within_tolerance: StrictBool

    @model_validator(mode="after")
    def _difference(self) -> Self:
        if self.difference != self.statement_paid - self.book_expected:
            raise ValueError("difference must equal statement_paid minus book_expected")
        return self


class Totals(StrictModel):
    """tie_out/totals_by_carrier.json and totals_by_agent.json."""

    group_by: Literal["carrier", "agent"]
    status: LegStatus
    not_run_reason: OptionalText
    rows: tuple[TotalRow, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.status == LegStatus.NOT_RUN) != (self.not_run_reason is not None):
            raise ValueError("not_run_reason is required exactly when totals did not run")
        if self.status == LegStatus.NOT_RUN and self.rows:
            raise ValueError("totals that did not run have no rows")
        if len({row.key for row in self.rows}) != len(self.rows):
            raise ValueError("each carrier or agent appears once")
        return self


class RtsCell(StrictModel):
    npn: NonEmpty
    carrier: NonEmpty
    state: NonEmpty
    plan_year: StrictInt
    coverage: RtsCellState
    policy_count: Count  # policies this agent wrote for this carrier, state, and year
    exception_ids: tuple[NonEmpty, ...]  # the RTS-001 records behind a gap

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.policy_count == 0) != (self.coverage == RtsCellState.HELD_UNUSED):
            raise ValueError("only HELD_UNUSED cells have zero policies")
        gap = self.coverage == RtsCellState.USED_WITHOUT_RTS
        if len(self.exception_ids) != (self.policy_count if gap else 0):
            raise ValueError("a USED_WITHOUT_RTS cell lists one RTS-001 per policy; others none")
        return self


class RtsCoverage(StrictModel):
    """rts_coverage.json. Empty when a blocker stopped the run."""

    cells: tuple[RtsCell, ...]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        keys = {(c.npn, c.carrier, c.state, c.plan_year) for c in self.cells}
        if len(keys) != len(self.cells):
            raise ValueError("each agent, carrier, state, and plan year appears once")
        return self


class DetectionClass(StrictModel):
    defect_class: NonEmpty
    scored: StrictBool  # unscored identity defects are reported, not gated
    planted: Count
    detected: Count  # recall is detected / planted, computed by the reader

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        if self.detected > self.planted:
            raise ValueError("detected cannot exceed planted")
        return self


class DetectionSummary(StrictModel):
    """Accuracy against ground_truth.json, when the drop has one."""

    classes: tuple[DetectionClass, ...]
    false_positive_rate: Probability


class Scorecard(StrictModel):
    run_id: NonEmpty
    status: RunStatus
    rows_in: Count
    rows_mapped: Count
    rows_clean: Count
    exceptions_by_severity: SeverityCounts
    exceptions_by_rule: dict[Annotated[str, Field(pattern=r"^[A-Z]{3}-\d{3}$")], Count]
    tie_out: tuple[LegSummary, ...]  # exactly one per leg, in leg order
    rts_gaps: Count  # USED_WITHOUT_RTS cells in rts_coverage.json
    detection: DetectionSummary | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        counts = self.exceptions_by_severity
        if not self.rows_clean <= self.rows_mapped <= self.rows_in:
            raise ValueError("rows can only shrink: rows_clean <= rows_mapped <= rows_in")
        if sum(self.exceptions_by_rule.values()) != sum(counts.model_dump().values()):
            raise ValueError("exceptions_by_rule and exceptions_by_severity disagree")
        if [leg.leg for leg in self.tie_out] != list(TieOutLeg):
            raise ValueError("tie_out needs exactly one summary per leg, in leg order")
        failed = self.status == RunStatus.FAILED
        if failed != (counts.blocker > 0) or (failed and self.rows_clean):
            raise ValueError("FAILED means at least one blocker and no clean rows")
        if (self.status == RunStatus.PASSED) != (
            counts.blocker + counts.error + counts.warning == 0
        ):
            raise ValueError("PASSED means zero exceptions above info")
        if self.status == RunStatus.PASSED and any(
            leg.status == LegStatus.NOT_RUN for leg in self.tie_out
        ):
            raise ValueError("a run with a leg that did not run cannot be PASSED")
        return self


# Every JSON file in a run directory and its model. exceptions.jsonl holds ExceptionRecords.
RUN_FILE_MODELS: dict[str, type[StrictModel]] = {
    "manifest.json": Manifest,
    "scorecard.json": Scorecard,
    "rts_coverage.json": RtsCoverage,
    **{f"tie_out/leg_{stem}.json": LegResult for stem in TieOutLeg.file_stems()},
    "tie_out/variances.json": VarianceReport,
    "tie_out/totals_by_carrier.json": Totals,
    "tie_out/totals_by_agent.json": Totals,
}
