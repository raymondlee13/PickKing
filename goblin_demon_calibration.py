"""Goblin/Demon payout-multiplier calibration.

PrizePicks doesn't expose real per-leg multipliers for alt (goblin/demon)
lines through the PropLine feed -- `payout_multiplier` is present in the raw
outcome schema but has been null on every example checked so far. Grading a
goblin/demon leg against the same break-even bar as a standard line is wrong
in opposite directions: goblins pay less than standard (safer line, lower
multiplier) so they look inflated to Tier A, demons pay more (riskier line,
higher multiplier) so they look suppressed. This module estimates the real
per-leg multiplier from hand-verified examples, stored in
goblin_demon_calibration.json so the app can grow the table at runtime (see
record_correction) instead of needing a code change for every new data point.

IMPORTANT -- what's stored is NOT a standalone per-leg multiplier. Every
value is the observed TOTAL multiplier of a real 2-pick Power entry built
from one standard leg plus one alt leg (confirmed against the app -- see
chat). To isolate what the alt leg alone contributes, estimate_multiplier
divides that total by the standard leg's own known fair multiplier for a
2-pick entry (derived from POWER_PLAY_BARS[2] in scoring.py and passed in by
the caller, so this module doesn't need to import scoring.py). Skipping that
division was tried first and produced backwards results -- goblins came out
with a *lower* bar than standard, demons with a *higher* one, the opposite of
reality -- caught by testing before it shipped.

Deviation is (alt line's point) minus (the standard line's point): negative
for goblins (line moved down, easier to hit), positive for demons (line
moved up, harder). PropLine already computes this for us as `line_gap` on
the raw outcome, so scoring.py reads it directly rather than reconstructing
it from consensus books.

Confirmed markets differ a lot at the same raw deviation (e.g. +4 on
rebounds hit 11x for Kiah Stokes, +4 on PRA only hit 4.25x for Jonquel
Jones) -- a low-mean stat like rebounds/assists swings much harder per point
than points/PRA. So calibration is kept per-market rather than shared
across markets. A market with no entries here just falls back to the flat
entry-size bar (today's pre-calibration behavior).
"""

import json
import math
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CALIBRATION_PATH = os.path.join(BASE_DIR, "goblin_demon_calibration.json")


def _load_calibration():
    if not os.path.exists(CALIBRATION_PATH):
        return {}
    with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {market: {dfs_type: [tuple(p) for p in points] for dfs_type, points in by_type.items()}
            for market, by_type in raw.items()}


def _save_calibration():
    serializable = {market: {dfs_type: [list(p) for p in points] for dfs_type, points in by_type.items()}
                     for market, by_type in CALIBRATION.items()}
    with open(CALIBRATION_PATH, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)


# {market_key: {"goblin": [(deviation, observed 2-pick total multiplier), ...], "demon": [...]}}
# Loaded once at import; record_correction mutates this in place and persists it.
CALIBRATION = _load_calibration()


def _interpolate_total_multiplier(table, deviation):
    points = sorted(table, key=lambda p: p[0])
    if len(points) == 1:
        return points[0][1]

    if deviation <= points[0][0]:
        (d0, m0), (d1, m1) = points[0], points[1]
    elif deviation >= points[-1][0]:
        (d0, m0), (d1, m1) = points[-2], points[-1]
    else:
        d0, m0 = points[0]
        for d1, m1 in points[1:]:
            if deviation <= d1:
                break
            d0, m0 = d1, m1

    if d1 == d0:
        return m0
    t = (deviation - d0) / (d1 - d0)
    log_m = math.log(m0) + t * (math.log(m1) - math.log(m0))
    return math.exp(log_m)


def estimate_multiplier(market_key, dfs_type, deviation, reference_leg_multiplier):
    """Estimated standalone multiplier for one alt (goblin/demon) leg, or
    None if there's no calibration data yet for this market/type.

    reference_leg_multiplier is the standard leg's own fair multiplier for
    the entry size these examples were captured at (2-pick Power, so far) --
    the observed 2-pick total is divided by it to isolate the alt leg's own
    contribution.
    """
    table = CALIBRATION.get(market_key, {}).get(dfs_type)
    if not table:
        return None

    observed_total = _interpolate_total_multiplier(table, deviation)
    return observed_total / reference_leg_multiplier


def record_correction(market_key, dfs_type, deviation, observed_total_multiplier):
    """Add or update a calibration point from a real observed 2-pick total
    multiplier (this leg + one standard leg), then persist it to disk so it
    sharpens every future estimate for this market/type, not just this leg.
    """
    deviation = round(float(deviation), 1)
    observed_total_multiplier = float(observed_total_multiplier)

    table = CALIBRATION.setdefault(market_key, {}).setdefault(dfs_type, [])
    for i, (d, _m) in enumerate(table):
        if abs(d - deviation) < 0.05:
            table[i] = (deviation, observed_total_multiplier)
            break
    else:
        table.append((deviation, observed_total_multiplier))
    table.sort(key=lambda p: p[0])

    _save_calibration()
