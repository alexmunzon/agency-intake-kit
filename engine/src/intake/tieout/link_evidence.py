from decimal import Decimal
from typing import Literal, Self, cast

import duckdb
from pydantic import Field, model_validator

from agency_schema.lineage import Lineage, NonEmpty, StrictModel
from intake.tieout.prepare import Prepared
from intake.tieout.views import rows

Method = Literal["MEMBER_ID", "POLICY_REF", "NAME_DOB"]
State = Literal["confirmed", "provisional", "ambiguous", "unmatched"]
LinkReason = Literal[
    "strong_key",
    "name_dob_only",
    "multiple_candidates",
    "unmatched_strong_key",
    "conflicting_name_dob",
    "no_candidate",
]
METHODS = ("MEMBER_ID", "POLICY_REF", "NAME_DOB")


class Candidate(StrictModel):
    policy_id: NonEmpty
    methods: tuple[Method, ...] = Field(min_length=1)
    lineage: Lineage


class LinkEvidence(StrictModel):
    schema_version: Literal[1] = 1
    lineage: Lineage
    state: State
    reason: LinkReason
    policy_id: NonEmpty | None
    amount: Decimal | None
    candidates: tuple[Candidate, ...]

    @model_validator(mode="after")
    def valid_state(self) -> Self:
        reasons = {
            "confirmed": {"strong_key"},
            "provisional": {"name_dob_only"},
            "ambiguous": {"multiple_candidates", "unmatched_strong_key", "conflicting_name_dob"},
            "unmatched": {"no_candidate"},
        }
        if self.reason not in reasons[self.state]:
            raise ValueError("link reason does not match state")
        ids = [candidate.policy_id for candidate in self.candidates]
        if any(candidate.lineage.run_id != self.lineage.run_id for candidate in self.candidates):
            raise ValueError("candidate lineage run_id differs from statement lineage")
        if self.state == "confirmed":
            strong = [
                c.policy_id for c in self.candidates if {"MEMBER_ID", "POLICY_REF"} & set(c.methods)
            ]
            weak = {c.policy_id for c in self.candidates if "NAME_DOB" in c.methods}
            if strong != [self.policy_id] or (weak and self.policy_id not in weak):
                raise ValueError("confirmed link needs one consistent strong candidate")
        elif self.policy_id is not None:
            raise ValueError("only a confirmed link may attribute a policy")
        elif self.state == "provisional" and (
            len(ids) != 1 or set(self.candidates[0].methods) != {"NAME_DOB"}
        ):
            raise ValueError("provisional link needs one NAME_DOB-only candidate")
        elif self.state == "ambiguous" and not ids:
            raise ValueError("ambiguous link needs a candidate")
        elif self.state == "unmatched" and ids:
            raise ValueError("unmatched link cannot have candidates")
        return self


def collect_links(con: duckdb.DuckDBPyConnection, prepared: Prepared) -> tuple[LinkEvidence, ...]:
    edges: dict[int, dict[str, tuple[int, set[Method]]]] = {}
    for edge in rows(con, "line_candidates"):
        rec, policy_rec = int(edge["_rec"]), int(edge["policy_rec"])
        policy_id, raw_method = edge["policy_id"], edge["match_method"]
        if not isinstance(policy_id, str) or not policy_id or raw_method not in METHODS:
            raise ValueError("invalid candidate edge")
        by_policy = edges.setdefault(rec, {})
        if policy_id in by_policy:
            old_rec, methods = by_policy[policy_id]
            if old_rec != policy_rec:
                raise ValueError("one candidate policy ID has multiple source rows")
            methods.add(cast(Method, raw_method))
        else:
            by_policy[policy_id] = (policy_rec, {cast(Method, raw_method)})

    output: list[LinkEvidence] = []
    for match in rows(con, "line_match"):
        rec = int(match["_rec"])
        candidates = tuple(
            Candidate(
                policy_id=policy_id,
                methods=tuple(sorted(methods, key=METHODS.index)),
                lineage=prepared.lineage["policies"][policy_rec],
            )
            for policy_id, (policy_rec, methods) in sorted(edges.get(rec, {}).items())
        )
        amount = match["amount"]
        output.append(
            LinkEvidence(
                lineage=prepared.lineage["commission_lines"][rec],
                state=cast(State, match["link_state"]),
                reason=cast(LinkReason, match["link_reason"]),
                policy_id=match["policy_id"],
                amount=None if amount is None else Decimal(str(amount)),
                candidates=candidates,
            )
        )
    return tuple(
        sorted(
            output,
            key=lambda link: (
                link.lineage.source_file,
                link.lineage.sheet or "",
                link.lineage.row_number,
            ),
        )
    )
