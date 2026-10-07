"""Checks for the grading math every tier depends on. Run: python test_scoring.py"""

import goblin_demon_calibration as cal
from scoring import (
    POWER_PLAY_BARS, STANDARD_2PICK_LEG_MULTIPLIER, american_to_prob, devig_two_way,
    LADDER_MAX_PROB, TIER_S_MARGIN, _grade_leg, cap_tier, estimate_probability_from_ladder, grade_leg,
    extract_consensus, fit_poisson_mean, ladder_extrapolated, poisson_binomial_dist, poisson_over, row_sort_key,
    shift_over_prob,
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


def _event(prices):
    """A one-player event: {book: (over_price, under_price)} at Over/Under 20.5 points."""
    return {"bookmakers": [
        {"key": book, "markets": [{"key": "player_points", "outcomes": [
            {"name": "Over", "description": "X", "point": 20.5, "price": over},
            {"name": "Under", "description": "X", "point": 20.5, "price": under},
        ]}]} for book, (over, under) in prices.items()]}


LEG = {"player": "X", "market": "player_points", "point": 20.5, "dfs_odds_type": "standard", "line_gap": None}


def test_consensus_is_median_not_mean():
    fair = (-150, 150)  # 60% fair
    one_off = _event({"draftkings": fair, "fanduel": fair, "bovada": (-400, 400)})  # one book way off
    row = _grade_leg(one_off, LEG, 55.0)
    assert close(row["consensus_pct"], 60.0, tol=0.05)  # the mean would be ~65
    assert [p[0] for p in row["book_prices"]] == ["draftkings", "fanduel", "bovada"]
    assert row["book_prices"][2][2:] == [-400, 400]


def test_single_book_capped_at_tier_c():
    strong = (-300, 300)  # 75% -> margin 20 over a 55 bar, would be TIER S
    row = _grade_leg(_event({"draftkings": strong}), LEG, 55.0)
    assert row["single_book"] and row["tier"] == "TIER C" and row["tier_capped"]
    assert row["margin"] > TIER_S_MARGIN  # the real margin still shows
    two = _grade_leg(_event({"draftkings": strong, "fanduel": strong}), LEG, 55.0)
    assert two["tier"] == "TIER S" and not two["tier_capped"]
    assert cap_tier("TIER A", True) == "TIER C" and cap_tier("BELOW BAR", True) == "BELOW BAR"
    # A capped C with a huge margin must still sort below a real (smaller-margin) B.
    real_b = {"tier": "TIER B", "margin": 4.0, "consensus_pct": 59.0}
    assert row_sort_key(real_b) > row_sort_key(row)


def test_poisson_gap_shift():
    # Fitting reproduces the book's own price exactly.
    assert close(poisson_over(6.5, fit_poisson_mean(6.5, 0.47)), 0.47)
    # One rebound easier is worth ~16 points -- the old code reused 47% for it.
    assert close(shift_over_prob(6.5, 0.47, 5.5), 0.628, tol=0.005)
    assert shift_over_prob(6.5, 0.47, 7.5) < 0.47
    # Whole-number line: push dropped, so it sits between the two half lines.
    assert 0.47 < shift_over_prob(6.5, 0.47, 6) < 0.628


def test_gap_only_for_markets_that_passed_the_check():
    def event(market, book_line):
        return {"bookmakers": [{"key": "draftkings", "markets": [{"key": market, "outcomes": [
            {"name": "Over", "description": "X", "point": book_line, "price": 110},
            {"name": "Under", "description": "X", "point": book_line, "price": -130}]}]}]}
    # Rebounds didn't qualify: a line 1 away is no longer used at all (was reused as-is).
    assert extract_consensus(event("player_rebounds", 6.5), "X", "player_rebounds", 5.5) == []
    # Threes did: the book's 6.5 price is shifted to 5.5, not copied.
    got = extract_consensus(event("player_threes", 3.5), "X", "player_threes", 2.5)[0]
    book_p = devig_two_way(american_to_prob(110), american_to_prob(-130))
    assert not got["is_exact_match"] and close(got["novig_over_prob"], shift_over_prob(3.5, book_p, 2.5))
    assert got["novig_over_prob"] > book_p + 0.1


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
