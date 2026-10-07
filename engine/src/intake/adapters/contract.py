"""Agency integration contract 1.0.0. Keep identical in all three adapters."""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

Text = Annotated[str, Field(min_length=1)]
Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ReviewState = Literal["not_reviewed", "needs_review", "approved", "rejected", "blocked"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Artifact(ContractModel):
    path: Text
    sha256: Sha
    size_bytes: Annotated[StrictInt, Field(ge=0)]


class Provenance(ContractModel):
    source_file: Text
    sheet: Text | None
    row_number: Annotated[StrictInt, Field(ge=1)]
    raw_hash: Sha
    run_id: Text
    mapping_version: Text
    artifact: Text
    artifact_row: Annotated[StrictInt, Field(ge=1)]


class Client(ContractModel):
    record_id: Text
    client_id: Text
    first_name: str | None
    last_name: str | None
    dob: date | None
    mbi: str | None
    phone: str | None
    email: str | None
    address_line1: str | None
    city: str | None
    state: str | None
    zip: str | None
    household_id: str | None
    warnings: tuple[str, ...] = ()
    provenance: Provenance


class Policy(ContractModel):
    record_id: Text
    policy_id: Text
    client_id: Text
    plan_id: Text
    line_of_business: Text
    status: Text
    effective_date: date
    termination_date: date | None
    provenance: Provenance


class Issue(ContractModel):
    code: Text
    record_ids: tuple[str, ...] = ()
    artifact: str | None = None
    artifact_row: Annotated[StrictInt, Field(ge=1)] | None = None
    review_state: ReviewState = "needs_review"


class Identity(ContractModel):
    person_id: Text | None
    record_ids: tuple[Text, ...]
    client_ids: tuple[Text, ...]
    state: Literal["resolved", "unresolved", "ambiguous", "unsupported"]
    review_state: ReviewState
    reasons: tuple[str, ...] = ()


class Packet(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    agency_id: Text
    run_id: Text
    intake_run_id: Text
    data_kind: Literal["synthetic"]
    artifacts: tuple[Artifact, ...]
    clients: tuple[Client, ...]
    policies: tuple[Policy, ...]
    identities: tuple[Identity, ...] = ()
    issues: tuple[Issue, ...] = ()

    @model_validator(mode="after")
    def references(self) -> Self:
        paths = [a.path for a in self.artifacts]
        rows: tuple[Client | Policy, ...] = (*self.clients, *self.policies)
        ids = [r.record_id for r in rows]
        if len(set(paths)) != len(paths) or len(set(ids)) != len(ids):
            raise ValueError("duplicate artifact path or record ID")
        for row in rows:
            if row.provenance.run_id != self.intake_run_id:
                raise ValueError("provenance run does not match Intake run")
            if row.provenance.artifact not in paths:
                raise ValueError("provenance artifact is not pinned")
        by_id = {c.record_id: c.client_id for c in self.clients}
        linked: list[str] = []
        for identity in self.identities:
            if not identity.record_ids or any(r not in by_id for r in identity.record_ids):
                raise ValueError("identity references an unknown client record")
            if set(identity.client_ids) != {by_id[r] for r in identity.record_ids}:
                raise ValueError("identity client IDs disagree with linked records")
            if identity.state == "resolved" and (
                len(set(identity.record_ids)) < 2 or identity.person_id is None
            ):
                raise ValueError("resolved identity requires multiple records and a person ID")
            linked.extend(identity.record_ids)
        if self.identities and (len(linked) != len(set(linked)) or set(linked) != set(by_id)):
            raise ValueError("identities must partition all client records exactly once")
        return self


class Coverage(ContractModel):
    agency_id: Text
    client_id: Text
    policy_id: Text
    plan_id: Text | None
    plan_year: Annotated[StrictInt, Field(ge=2000, le=2100)] | None
    county: Text | None
    provenance: Provenance


class CoverageFile(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    data_kind: Literal["synthetic"]
    artifacts: tuple[Artifact, ...]
    rows: tuple[Coverage, ...]


def canonical_json(model: BaseModel) -> str:
    return (
        json.dumps(
            model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        + "\n"
    )


def stable_id(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError("artifact path must stay inside input directory")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()) or target == root.resolve():
        raise ValueError("artifact path escapes input directory")
    return target


def pin(root: Path, relative: str) -> Artifact:
    data = safe_path(root, relative).read_bytes()
    return Artifact(path=relative, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))


def read_pinned(root: Path, artifact: Artifact) -> bytes:
    data = safe_path(root, artifact.path).read_bytes()
    if len(data) != artifact.size_bytes or hashlib.sha256(data).hexdigest() != artifact.sha256:
        raise ValueError(f"stale artifact: {artifact.path}")
    return data


def verify(root: Path, packet: Packet) -> None:
    for artifact in packet.artifacts:
        read_pinned(root, artifact)
