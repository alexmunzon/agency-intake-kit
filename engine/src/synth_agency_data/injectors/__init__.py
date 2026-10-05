"""Error injectors: labeled defects on a copy of the clean world, with guide 7.3 default rates.

The order matters. Identity edits run before the copied-client injectors, so a copy is made
from a client that is already final. Each defected record is locked, so no record carries two
defects and scoring by record key is unambiguous. Rates describe fake data, so they live here,
not in intake/config.py.
"""

import random
from dataclasses import replace

from synth_agency_data.injectors import clients as c
from synth_agency_data.injectors import commissions as m
from synth_agency_data.injectors import policies as p
from synth_agency_data.injectors import roster as r
from synth_agency_data.injectors.base import Defect, Injector, lock_key
from synth_agency_data.world import World

__all__ = ["INJECTORS", "Defect", "inject", "lock_key"]

INJECTORS: tuple[tuple[Injector, float], ...] = (
    (c.zip_state_mismatch, 0.01),
    (c.invalid_mbi, 0.01),
    (c.missing_mbi, 0.02),
    (p.npn_malformed, 0.005),
    (p.unknown_writing_agent, 0.005),
    (p.plan_id_malformed, 0.01),
    (p.term_before_effective, 0.005),
    (p.status_date_conflict, 0.01),
    (p.messy_status, 0.02),
    (p.exact_duplicate_row, 0.01),
    (p.duplicate_policy_id, 0.003),
    (p.orphan_policy, 0.005),
    (m.orphan_commission_line, 0.01),
    (m.missing_commission_line, 0.02),
    (m.commission_off_schedule, 0.01),
    (p.crm_status_conflict, 0.015),
    (r.rts_gap, 0.01),
    (r.rts_expired, 0.003),
    (r.license_gap, 0.005),
    # Unscored: injected for bob-resolve, reported here but not gated.
    (c.name_typo, 0.02),
    (c.nickname, 0.03),
    (c.dob_transposition, 0.01),
    (c.dob_month_day_swap, 0.005),
    (c.name_dob_collision, 0.005),  # scored, but must copy a client after the identity edits
    (c.near_duplicate_client, 0.015),
)


def inject(world: World) -> tuple[World, list[Defect]]:
    """Plant SPEC examples 3 and 4, then run every injector at its default rate."""
    from synth_agency_data.planted import plant  # planted.py imports injectors.base

    rng = random.Random(f"inject-{world.seed}")
    world, defects = plant(world)
    for fn, rate in INJECTORS:
        world, new = fn(world, rng, rate)
        world = replace(world, locked=world.locked | {lock_key(d["record_key"]) for d in new})
        defects += new
    # Not an injector: the totals the line injectors above pushed past tolerance (TIE-005).
    return world, defects + m.total_variances(world)
