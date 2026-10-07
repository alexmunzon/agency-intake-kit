"""Export actual Intake clean CSVs with their original provenance and review evidence."""

import csv
import io
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import Manifest
from intake.adapters.contract import (
    Client,
    Issue,
    Packet,
    Policy,
    Provenance,
    pin,
    read_pinned,
    stable_id,
)
from intake.run.unresolved_evidence import UnresolvedEvidence


def export_run(root: Path, *, agency_id: str, data_kind: Literal["synthetic"]) -> Packet:
    """Caller explicitly attests synthetic inputs. Never reads raw drops or ground truth."""
    manifest_pin = pin(root, "manifest.json")
    manifest = Manifest.model_validate_json(read_pinned(root, manifest_pin))
    artifacts = [manifest_pin]
    issues: list[Issue] = []
    clients: list[Client] = []
    policies: list[Policy] = []
    review_models: list[tuple[str, type[ExceptionRecord] | type[UnresolvedEvidence]]] = [
        ("exceptions.jsonl", ExceptionRecord),
        ("unresolved_evidence.jsonl", UnresolvedEvidence),
    ]
    for path, model in review_models:
        if not (root / path).exists():
            issues.append(Issue(code="MISSING_REVIEW_EVIDENCE", artifact=path))
            continue
        artifact = pin(root, path)
        artifacts.append(artifact)
        for index, line in enumerate(read_pinned(root, artifact).decode().splitlines(), 1):
            if not line.strip():
                continue
            evidence_row = model.model_validate_json(line)
            if (
                isinstance(evidence_row, UnresolvedEvidence)
                and evidence_row.run_id != manifest.run_id
            ):
                raise ValueError("review evidence belongs to a different Intake run")
            if evidence_row.lineage and evidence_row.lineage.run_id != manifest.run_id:
                raise ValueError("review lineage belongs to a different Intake run")
            code = (
                evidence_row.rule_id
                if isinstance(evidence_row, ExceptionRecord)
                else evidence_row.reason
            )
            issues.append(Issue(code=code, artifact=path, artifact_row=index))
    failed = manifest.status == "FAILED"
    if failed:
        issues.append(Issue(code="INTAKE_FAILED", review_state="blocked"))
    tables: list[tuple[str, type[Client] | type[Policy]]] = [
        ("clients", Client),
        ("policies", Policy),
    ]
    for table, cls in tables:
        path = f"clean/{table}.csv"
        if failed or not (root / path).exists():
            issues.append(Issue(code="MISSING_CLEAN_TABLE", artifact=path, review_state="blocked"))
            continue
        artifact = pin(root, path)
        artifacts.append(artifact)
        reader = csv.DictReader(
            io.StringIO(read_pinned(root, artifact).decode("utf-8-sig")), strict=True
        )
        try:
            headers = reader.fieldnames or []
        except csv.Error:
            issues.append(Issue(code="INVALID_CLEAN_COLUMNS", artifact=path))
            continue
        required = set(cls.model_fields) - {"record_id", "provenance", "warnings"}
        required |= {
            f"lineage_{k}" for k in Provenance.model_fields if k not in {"artifact", "artifact_row"}
        }
        if len(headers) != len(set(headers)) or not required <= set(headers):
            issues.append(Issue(code="INVALID_CLEAN_COLUMNS", artifact=path))
            continue
        index = 0
        while True:
            try:
                raw = next(reader)
            except StopIteration:
                break
            except csv.Error:
                issues.append(
                    Issue(code="INVALID_CLEAN_ROW", artifact=path, artifact_row=index + 1)
                )
                break
            index += 1
            try:
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError("invalid clean row width")
                values: dict[str, Any] = {
                    k: raw.get(k) or None
                    for k in cls.model_fields
                    if k not in {"record_id", "provenance", "warnings"}
                }
                provenance: dict[str, Any] = {
                    k: raw.get(f"lineage_{k}") or None
                    for k in Provenance.model_fields
                    if k not in {"artifact", "artifact_row"}
                }
                provenance["row_number"] = int(raw["lineage_row_number"])
                values["provenance"] = Provenance(**provenance, artifact=path, artifact_row=index)
                if values["provenance"].run_id != manifest.run_id:
                    raise ValueError("wrong lineage run")
                values["record_id"] = stable_id(
                    agency_id, manifest.run_id, table, artifact.sha256, str(index)
                )
                if cls is Client:
                    values["warnings"] = tuple(filter(None, (raw.get("warnings") or "").split("|")))
                    clients.append(Client(**values))
                else:
                    policies.append(Policy(**values))
            except (ValidationError, ValueError, KeyError, TypeError):
                issues.append(Issue(code="INVALID_CLEAN_ROW", artifact=path, artifact_row=index))
    groups: list[tuple[Sequence[Client | Policy], str]] = [
        (clients, "client_id"),
        (policies, "policy_id"),
    ]
    for rows, key in groups:
        counts = Counter(getattr(r, key) for r in rows)
        for row in rows:
            if counts[getattr(row, key)] > 1:
                issues.append(Issue(code=f"DUPLICATE_{key.upper()}", record_ids=(row.record_id,)))
    ids = {c.client_id for c in clients}
    issues.extend(
        Issue(code="MISSING_CLIENT", record_ids=(p.record_id,))
        for p in policies
        if p.client_id not in ids
    )
    return Packet(
        agency_id=agency_id,
        run_id=manifest.run_id,
        intake_run_id=manifest.run_id,
        data_kind=data_kind,
        artifacts=tuple(artifacts),
        clients=tuple(clients),
        policies=tuple(policies),
        issues=tuple(issues),
    )
