"""Reusable, deterministic onboarding archive using Session 1 artifact pins.

This is a readiness extension, not a fabricated clean-record Packet. Before Intake,
intake_run_id is explicitly null; file evidence has no invented row lineage.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from pydantic import Field, StrictInt

from agency_schema.lineage import Sha256, StrictModel
from intake.source_readiness import ReadinessPackage, Text, evaluate, parse_package


class ArtifactPin(StrictModel):
    """Wire-compatible with Session 1 intake.adapters.contract.Artifact."""

    path: Text
    sha256: Sha256
    size_bytes: Annotated[StrictInt, Field(ge=0)]


class OnboardingManifest(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_type: Literal["source_readiness_onboarding"] = "source_readiness_onboarding"
    agency_id: Text
    run_id: Text
    intake_run_id: Text | None
    data_kind: Literal["synthetic"] = "synthetic"
    review_state: Literal["not_reviewed"] = "not_reviewed"
    artifacts: tuple[ArtifactPin, ...]


def canonical_json(model: StrictModel) -> bytes:
    return (
        json.dumps(
            model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")


def export_package(package: ReadinessPackage, destination: Path) -> None:
    """Publish once, atomically, without overwriting evidence or existing output."""
    # Revalidate even a caller-created model; export never trusts forged computed state.
    package = parse_package(package.model_dump_json())
    files = {
        "source_readiness.json": canonical_json(package),
        "readiness_summary.json": canonical_json(evaluate(package)),
        **{f"evidence/{e.sha256}.txt": e.content.encode("utf-8") for e in package.evidence},
    }
    manifest = OnboardingManifest(
        agency_id=package.agency_id,
        run_id=package.run_id,
        intake_run_id=package.intake_run_id,
        artifacts=tuple(
            ArtifactPin(path=path, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
            for path, data in sorted(files.items())
        ),
    )
    files["onboarding_manifest.json"] = canonical_json(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".onboarding-", dir=destination.parent)
    try:
        with os.fdopen(fd, "w+b") as handle:
            with ZipFile(handle, "w", compression=ZIP_STORED) as archive:
                for path, data in sorted(files.items()):
                    # Fixed ZIP timestamps and ordering make reruns byte-identical.
                    archive.writestr(ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0)), data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)  # exclusive atomic publication on the same filesystem
    finally:
        os.unlink(temporary)
