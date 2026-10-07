"""Regenerate a small real Intake output using synthetic inputs; no truth is exported."""

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from agency_schema.outputs import JevMode
from intake.adapters.contract import canonical_json
from intake.adapters.export import export_run
from intake.run.pipeline import RunOptions, run
from synth_agency_data.world import build_world
from synth_agency_data.writers import write_drop

DEST = Path(__file__).parent
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    write_drop(build_world(seed=42, n_clients=8), [], root / "drop", plant_pii=False)
    result = run(
        RunOptions(
            drop=root / "drop",
            out=root / "intake-synthetic-v1",
            jev_mode=JevMode.OFF,
            as_of=datetime(2026, 10, 1, tzinfo=UTC),
        )
    )
    packet = export_run(
        result.run_dir, agency_id="synthetic-agency-a", data_kind="synthetic"
    )
    for artifact in packet.artifacts:
        destination = DEST / "intake-run" / artifact.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(result.run_dir / artifact.path, destination)
    (DEST / "intake-packet.json").write_text(canonical_json(packet))
