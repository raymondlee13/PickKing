"""Checks for the grading math every tier depends on. Run: python test_scoring.py"""

import goblin_demon_calibration as cal
from scoring import (
    POWER_PLAY_BARS, STANDARD_2PICK_LEG_MULTIPLIER, american_to_prob, devig_two_way,
    LADDER_MAX_PROB, estimate_probability_from_ladder, grade_leg, ladder_extrapolated, poisson_binomial_dist,
)


def close(a, b, tol=1e-3):
    return abs(a - b) < tol


def test_odds_conversion():
    assert close(american_to_prob(-110), 110 / 210)
    assert close(american_to_prob(150), 0.4)
    assert american_to_prob(None) is None
    # Even juice both ways de-vigs to a coin flip.
    p = american_to_prob(-110)
    assert close(devig_two_way(p, p), 0.5)
    assert close(devig_two_way(0.6, 0.5), 0.6 / 1.1)


def test_grade_leg_tier_boundaries():
    bar = 55.0
    cases = [(56.4, "BELOW BAR"), (56.5, "TIER C"), (58.0, "TIER B"), (60.0, "TIER A"), (63.0, "TIER S")]
    for prob, tier in cases:
        margin, got = grade_leg(bar, prob)
        assert close(margin, prob - bar) and got == tier, (prob, got)


def test_standard_2pick_pays_3x():
    # Two standard legs at the 2-pick bar should multiply back to the real 3x payout.
    assert close(STANDARD_2PICK_LEG_MULTIPLIER ** 2, 3.0, tol=0.01)
    assert close(100.0 / STANDARD_2PICK_LEG_MULTIPLIER, POWER_PLAY_BARS[2])


def test_poisson_binomial():
    assert all(close(a, b) for a, b in zip(poisson_binomial_dist([0.5, 0.5]), [0.25, 0.5, 0.25]))
    dist = poisson_binomial_dist([0.6, 0.55, 0.7, 0.58])
    assert len(dist) == 5 and close(sum(dist), 1.0)
    assert close(dist[4], 0.6 * 0.55 * 0.7 * 0.58)


def test_ladder_interpolation():
    # Over 40.5 needs 41, halfway between the 40+ and 42+ rungs on a log scale.
    ladder = [(40, 0.5), (42, 0.125)]
    assert close(estimate_probability_from_ladder(ladder, 40.5), 0.25)
    assert estimate_probability_from_ladder([], 40.5) is None


def test_ladder_never_projects_past_its_rungs():
    ladder = [(3, 0.80), (5, 0.40)]
    # Goblin 1.5 needs 2 -- below the lowest rung. Old code projected this to ~100%;
    # all we really know is P(2+) >= P(3+).
    assert close(estimate_probability_from_ladder(ladder, 1.5), 0.80)
    assert ladder_extrapolated(ladder, 1.5) and not ladder_extrapolated(ladder, 3.5)
    # Above the top rung: projected down, never above the top rung itself.
    assert estimate_probability_from_ladder(ladder, 6.5) < 0.40
    # One rung says nothing about a higher line (5+ can't be as likely as 2+).
    assert estimate_probability_from_ladder([(2, 0.90)], 4.5) is None
    # Vigged near-certain prices get capped.
    assert estimate_probability_from_ladder([(2, 0.985), (3, 0.9)], 1.5) == LADDER_MAX_PROB


def test_goblin_demon_direction():
    # The backwards bug from goblin_demon_calibration.py's docstring: goblins must
    # pay LESS than a standard leg, demons MORE. Uses a fake table, not the real one.
    saved = cal.CALIBRATION
    try:
        cal.CALIBRATION = {"m": {"goblin": [(-2.0, 2.0)], "demon": [(0.0, 2.0), (2.0, 8.0)]}}
        goblin = cal.estimate_multiplier("m", "goblin", -2.0, STANDARD_2PICK_LEG_MULTIPLIER)
        demon = cal.estimate_multiplier("m", "demon", 2.0, STANDARD_2PICK_LEG_MULTIPLIER)
        assert goblin < STANDARD_2PICK_LEG_MULTIPLIER < demon
        # Log-linear midpoint between 2x and 8x totals is 4x.
        mid = cal.estimate_multiplier("m", "demon", 1.0, 1.0)
        assert close(mid, 4.0)
        assert cal.estimate_multiplier("unknown_market", "demon", 1.0, 1.0) is None
    finally:
        cal.CALIBRATION = saved


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} checks passed")
