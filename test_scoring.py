"""Checks for the grading math every tier depends on. Run: python test_scoring.py"""

import goblin_demon_calibration as cal
import scoring
from scoring import (
    POWER_PLAY_BARS, STANDARD_2PICK_LEG_MULTIPLIER, american_to_prob, devig_two_way,
    LADDER_MAX_PROB, TIER_S_MARGIN, _grade_leg, devig_methods, estimate_probability_from_ladder, grade_leg,
    extract_consensus, fit_mean, ladder_extrapolated, poisson_binomial_dist, row_sort_key, shape_over,
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


def test_single_book_keeps_real_tier_but_is_flagged():
    strong = (-300, 300)  # 75% -> margin 20 over a 55 bar
    row = _grade_leg(_event({"draftkings": strong}), LEG, 55.0)
    # Real tier, flagged single_book (the UI warns and auto-add skips it).
    assert row["single_book"] and row["tier"] == "TIER S" and row["margin"] > TIER_S_MARGIN
    two = _grade_leg(_event({"draftkings": strong, "fanduel": strong}), LEG, 55.0)
    assert two["tier"] == "TIER S" and not two["single_book"]
    # Tiered rows sort by tier first, then margin.
    real_b = {"tier": "TIER B", "margin": 4.0, "consensus_pct": 59.0}
    assert row_sort_key(row) > row_sort_key(real_b)


def test_worst_case_devig_and_books_line():
    assert [round(x, 3) for x in devig_methods(-110, -110)] == [0.5, 0.5, 0.5]  # even line: all agree
    mult, add, power = devig_methods(150, -180)
    assert power < add < mult  # on an underdog, power shades it most
    assert devig_methods(None, -110) == []
    # A lopsided favorite: graded on More; the worst method can't beat the normal grade.
    row = _grade_leg(_event({"draftkings": (-300, 240), "fanduel": (-280, 230)}), LEG, 55.0)
    assert row["side"] == "More" and row["worst_pct"] <= row["consensus_pct"]
    # Graded sides are usually the favorite, where the app's method is already the most cautious.
    under = _grade_leg(_event({"draftkings": (180, -220), "fanduel": (175, -215)}), LEG, 55.0)
    assert under["side"] == "Less" and under["worst_pct"] <= under["consensus_pct"]
    # The books' main line rides along for standard legs, so the UI can flag PrizePicks differing.
    assert row["books_line"] == 20.5
    assert _grade_leg(_event({"draftkings": (-300, 240)}), dict(LEG, dfs_odds_type="goblin"), 55.0)["books_line"] is None


def test_untraded_exchange_quotes_are_skipped():
    junk = _event({"novig": (257, -9900)})  # 27% built-in margin: nobody is trading this
    assert extract_consensus(junk, "X", "player_points", 20.5) == []
    mixed = _event({"novig": (257, -9900), "draftkings": (-150, 120)})
    assert [c["book"] for c in extract_consensus(mixed, "X", "player_points", 20.5)] == ["draftkings"]


def test_gap_shapes():
    for shape in (("poisson", None), ("count", 0.5), ("count", 3.0), ("scale", 0.3)):
        # Every shape reproduces the book's own price exactly -- the market sets the mean.
        assert close(shape_over(6.5, fit_mean(6.5, 0.47, shape), shape), 0.47)
        # An easier line is more likely, a harder one less; whole lines sit between.
        easier, harder = shift_over_prob(6.5, 0.47, 5.5, shape), shift_over_prob(6.5, 0.47, 7.5, shape)
        assert harder < 0.47 < easier
        assert 0.47 < shift_over_prob(6.5, 0.47, 6, shape) < easier
    # One rebound easier under Poisson is worth ~16 points -- the old code reused 47%.
    assert close(shift_over_prob(6.5, 0.47, 5.5), 0.628, tol=0.005)
    # count d=1 is Poisson's spread; a tighter shape moves more across a gap, a wider one less.
    assert close(shift_over_prob(6.5, 0.47, 5.5, ("count", 1.0)), 0.628, tol=0.01)
    assert shift_over_prob(6.5, 0.47, 5.5, ("count", 0.5)) > 0.628 > shift_over_prob(6.5, 0.47, 5.5, ("count", 2.0))


def test_gap_only_for_markets_with_a_tested_shape():
    def event(market, book_line):
        return {"bookmakers": [{"key": "draftkings", "markets": [{"key": market, "outcomes": [
            {"name": "Over", "description": "X", "point": book_line, "price": 110},
            {"name": "Under", "description": "X", "point": book_line, "price": -130}]}]}]}
    book_p = devig_two_way(american_to_prob(110), american_to_prob(-130))
    saved = dict(scoring.GAP_SHAPES)
    scoring.GAP_SHAPES.clear()
    scoring.GAP_SHAPES.update({"player_threes": ("count", 1.7, 1.0), "player_pass_yds": ("scale", 1.3, 10.0)})
    try:
        # Not listed: a line 1 away is not used at all (it used to be reused as-is).
        assert extract_consensus(event("player_rebounds", 6.5), "X", "player_rebounds", 5.5) == []
        # Listed: the book's price is shifted with that market's own shape, not copied.
        got = extract_consensus(event("player_threes", 3.5), "X", "player_threes", 2.5)[0]
        assert not got["is_exact_match"]
        assert close(got["novig_over_prob"], shift_over_prob(3.5, book_p, 2.5, ("count", 1.7)))
        assert got["novig_over_prob"] > book_p + 0.1
        # Each market's own max gap: 9 yards is in range, 11 isn't.
        assert extract_consensus(event("player_pass_yds", 240.5), "X", "player_pass_yds", 231.5)
        assert extract_consensus(event("player_pass_yds", 240.5), "X", "player_pass_yds", 229.5) == []
    finally:
        scoring.GAP_SHAPES.clear()
        scoring.GAP_SHAPES.update(saved)


def test_anytime_td_payout_follows_each_players_chance():
    saved = cal.CALIBRATION.get("player_anytime_td")
    try:
        # The old shape -- one payout at "0 from the line" -- can't say anything per player.
        cal.CALIBRATION["player_anytime_td"] = {"demon": [(0.0, 4.25)]}
        assert cal.estimate_multiplier("player_anytime_td", "demon", 20.0, 1.0) is None
        # One real payout: half as likely pays twice as much.
        cal.CALIBRATION["player_anytime_td"] = {"demon": [(20.0, 6.0)]}
        assert close(cal.estimate_multiplier("player_anytime_td", "demon", 10.0, 1.0), 12.0)
        # Two: the curve runs through both (log-log), and longer shots pay more.
        cal.CALIBRATION["player_anytime_td"] = {"demon": [(8.0, 15.0), (24.0, 6.0)]}
        assert close(cal.estimate_multiplier("player_anytime_td", "demon", 8.0, 1.0), 15.0)
        assert cal.estimate_multiplier("player_anytime_td", "demon", 12.0, 1.0) > cal.estimate_multiplier(
            "player_anytime_td", "demon", 20.0, 1.0)
        # Graded legs at the same 0.5 line now get different bars by player.
        def td_event(prices):
            books = [{"key": "novig", "markets": [{"key": "player_anytime_td", "outcomes": [
                o for player, (over, under) in prices.items() for o in (
                    {"name": "Over", "description": player, "point": 0.5, "price": over},
                    {"name": "Under", "description": player, "point": 0.5, "price": under})]}]}]
            books.append({"key": "prizepicks", "markets": [{"key": "player_anytime_td", "outcomes": [
                {"name": "Over", "description": p, "point": 0.5, "dfs_odds_type": "demon"} for p in prices]}]})
            return {"bookmakers": books}
        rows = {r["player"]: r for r in scoring.build_report(td_event({"Favorite": (110, -130), "Longshot": (800, -1100)}), 55.0)[0]}
        assert rows["Favorite"]["bar"] > rows["Longshot"]["bar"]  # likelier scorer, smaller payout, higher bar
    finally:
        if saved is None:
            cal.CALIBRATION.pop("player_anytime_td", None)
        else:
            cal.CALIBRATION["player_anytime_td"] = saved


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
