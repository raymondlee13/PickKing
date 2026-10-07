"""Edge-grading logic: consensus de-vigging, tiering, and report building.
Pure data transforms -- no network calls (see propline_api.py for those)."""

import math
import re
import statistics
from collections import defaultdict

from goblin_demon_calibration import estimate_multiplier

DFS_BOOKS = {"prizepicks", "underdog", "sleeper", "dabble"}
# Real-money books whose two-way prices feed the de-vigged consensus. Widened
# 2026-10-05 with the other priced books PropLine carries (US books, low-vig
# books, and the Novig/ProphetX exchanges). Deliberately left out: other
# pick'em apps (pick6, parlayplay -- same product as PrizePicks, not a market),
# sweepstakes/social books (fliff, rebet, sportzino, courtside), thin
# prediction markets (kalshi, polymarket_us, smarkets), and the softest
# offshore books (onexbet, betus).
CONSENSUS_BOOKS = {"draftkings", "fanduel", "betmgm", "caesars", "betrivers",
                    "pinnacle", "bovada", "unibet",
                    "fanatics", "hardrock", "betway", "betonlineag", "lowvig", "novig", "prophetx"}

POWER_PLAY_BARS = {2: 57.7, 3: 55.0, 4: 56.0, 5: 55.0, 6: 55.0}
# Per-leg break-even for Flex, solved via real multi-tier EV math (see chat) --
# assumes equal probability across legs, same caveat as the reference chart.
# Flex has no 2-pick option.
FLEX_BARS = {3: 57.7, 4: 55.0, 5: 54.3, 6: 54.2}
# 5-tier spread (widened from an original 3-tier BELOW BAR/B/A split) so a
# leg's badge reflects how far above the bar it clears, not just whether it
# does. Below TIER_C_MARGIN stays BELOW BAR; TIER_S is for truly exceptional
# edges. See grade_leg.
TIER_S_MARGIN = 8.0
TIER_A_MARGIN = 5.0
TIER_B_MARGIN = 3.0
TIER_C_MARGIN = 1.5
# Tiers a leg priced by only ONE book can't claim -- it's capped to TIER C.
SINGLE_BOOK_CAPPED_TIERS = {"TIER S", "TIER A", "TIER B"}
# The standard leg's own fair multiplier for a 2-pick Power entry, derived
# from POWER_PLAY_BARS[2] -- every goblin/demon calibration example so far
# was captured as a real 2-pick entry (one standard leg + one alt leg), so
# this is what estimate_multiplier divides that observed total by to isolate
# the alt leg's own contribution. See goblin_demon_calibration.py.
STANDARD_2PICK_LEG_MULTIPLIER = 100.0 / POWER_PLAY_BARS[2]
# The app no longer asks for entry type/size upfront (that's decided later, per
# real entry, in the entry builder using the actual payout multiplier). This is
# just a single fixed reference bar so legs still get an initial Tier/margin
# label to sort and filter by -- 3-pick Power's bar, the old default entry.
DEFAULT_BAR = POWER_PLAY_BARS[3]
# Markets require an EXACT line match by default. Grading a PrizePicks line
# off a book's price at a different line unchanged is worse than no grade: a
# 1-rebound gap is ~16 probability points, and the error always favors the
# losing side. The one exception: count stats in GAP_ADJUST_MARKETS, where a
# book line up to GAP_ADJUST_MAX away is shifted to PrizePicks' line with a
# Poisson fit (see shift_over_prob). Which markets qualify was decided by
# gap_adjust_check.py -- hide a book's real price at one line, predict it from
# its neighbor, keep the markets where that prediction lands close.
# From gap_adjust_check.py on 2026-10-07 live odds: these predicted a book's
# real price from a line 1 away within 1.4-2.3 pts (books pricing the SAME line
# differ by ~1-2 pts), vs 18-35 pts reusing the neighbor's price as-is.
# Rebounds (4.0), receptions (3.9) and assists (3.6) improved a lot but missed
# the 3-pt bar -- a dispersion-tuned shape is the next step for them. Points
# and yards aren't Poisson-shaped at all (5-7 pt misses). Re-run the check
# before adding a market.
GAP_ADJUST_MARKETS = {"batter_hits", "pitcher_strikeouts", "player_pass_tds", "player_threes"}
GAP_ADJUST_MAX = 1.0
# Ceiling on any threshold-ladder probability. Ladder prices are one-sided
# (no Under to de-vig against), so the vig stays in and inflates the
# near-certain end -- a -5000 "2+ rebounds" reads as 98% it isn't.
# ponytail: flat cap; swap for a real one-sided de-vig once the report's
# THRESHOLD_LADDER rows show where ladders actually land.
LADDER_MAX_PROB = 0.92

BASKETBALL_MARKETS = ["player_points", "player_rebounds", "player_assists",
                       "player_points_rebounds_assists", "player_threes",
                       "player_blocks", "player_steals"]

# NOTE: these MLB market key names follow the-odds-api's standard naming
# convention, which PropLine advertises compatibility with -- but this has
# NOT been confirmed against a real PropLine response yet. Treat this list
# as a starting guess to verify, the same way we verified WNBA market names,
# before trusting any MLB output.
# Confirmed against a real PropLine response for an actual MLB game (see chat) --
# batter_hits_runs_rbis and pitcher_outs verified present. batter_runs_scored
# and pitcher_walks were requested but did not appear for that game; kept in
# the list since absence in one game doesn't prove absence everywhere, but
# they're unconfirmed for PrizePicks specifically.
MLB_MARKETS = ["batter_hits", "batter_home_runs", "batter_rbis", "batter_hits_runs_rbis",
               "batter_runs_scored", "batter_stolen_bases", "batter_total_bases",
               "pitcher_strikeouts", "pitcher_hits_allowed", "pitcher_walks", "pitcher_outs"]

# Same caveat as MLB above: the-odds-api's standard naming convention, NOT yet
# confirmed against a real PropLine NFL response. Treat as a starting guess to
# verify before trusting any NFL output.
NFL_MARKETS = ["player_pass_yds", "player_pass_tds", "player_pass_completions",
               "player_pass_attempts", "player_pass_interceptions", "player_rush_yds",
               "player_rush_attempts", "player_receptions", "player_reception_yds",
               "player_pass_rush_reception_yds", "player_kicking_points",
               "player_field_goals", "player_anytime_td"]

MARKETS_BY_SPORT = {
    "basketball_wnba": BASKETBALL_MARKETS,
    "basketball_nba": BASKETBALL_MARKETS,
    "baseball_mlb": MLB_MARKETS,
    "americanfootball_nfl": NFL_MARKETS,
}

# Human league names for the API's sport keys -- used anywhere a key needs to
# read as a real word instead of an underscored slug (UI labels, and search
# queries in ai_context.py, where "basketball_wnba" or a bare team-only query
# reads to a search engine as much weaker evidence than "WNBA").
SPORT_LABELS = {
    "basketball_wnba": "WNBA",
    "basketball_nba": "NBA",
    "baseball_mlb": "MLB",
    "americanfootball_nfl": "NFL",
}


def get_max_gap(market_key):
    return GAP_ADJUST_MAX if market_key in GAP_ADJUST_MARKETS else 0.0


def poisson_over(line, lam):
    """P(Over `line`) for a Poisson count with mean lam. A whole-number line can
    push, and books price those with the push refunded, so it's P(over | no
    push) -- the same thing a de-vigged book price at that line means."""
    k = math.floor(line)
    pmf = math.exp(-lam)
    at_or_below = pmf  # P(X <= k), built up term by term (no factorial overflow)
    for i in range(1, k + 1):
        pmf *= lam / i
        at_or_below += pmf
    over = max(0.0, 1.0 - at_or_below)
    if line == k:  # whole number: drop the push
        return over / (1.0 - pmf) if pmf < 1.0 else 0.0
    return over


def fit_poisson_mean(line, over_prob):
    """The Poisson mean that makes P(Over `line`) equal over_prob (bisection --
    P(Over) only rises as the mean rises)."""
    lo, hi = 1e-6, 400.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if poisson_over(line, mid) < over_prob:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def shift_over_prob(book_line, over_prob, target_line):
    """A book's no-vig P(Over book_line), moved to target_line: fit the Poisson
    mean that reproduces the book's price, then read P(Over target_line) off it.
    Still anchored to the market -- the book sets the mean; Poisson only says
    how probability spreads across neighboring lines."""
    return poisson_over(target_line, fit_poisson_mean(book_line, over_prob))


def american_to_prob(price):
    if price is None:
        return None
    if price > 0:
        return 100.0 / (price + 100.0)
    return -price / (-price + 100.0)


def devig_two_way(over_prob, under_prob):
    if over_prob is None or under_prob is None:
        return None
    total = over_prob + under_prob
    return over_prob / total if total else None


def extract_raw_all_books(event):
    """Raw markets/outcomes across every bookmaker in the event, each tagged
    with its source book -- lets the in-app raw data viewer show PrizePicks'
    line next to every consensus book's for the same player/market, e.g. to
    check whether a consensus book has a usable line to compare a goblin/demon
    leg against when PropLine hasn't given us a line_gap for it."""
    combined = []
    for book in event.get("bookmakers", []):
        for market in book.get("markets", []):
            combined.append({
                "key": market.get("key"),
                "book": book.get("key"),
                "outcomes": market.get("outcomes", []),
            })
    return combined


def extract_pp_lines(event, board="prizepicks"):
    pp_lines = []
    for book in event.get("bookmakers", []):
        if book["key"] != board:
            continue
        for market in book.get("markets", []):
            by_player = defaultdict(dict)
            for outcome in market.get("outcomes", []):
                by_player[outcome.get("description")][outcome["name"]] = outcome
            for player, sides in by_player.items():
                over = sides.get("Over")
                if not over:
                    continue
                pp_lines.append({
                    "board": book["key"], "player": player, "market": market["key"],
                    "point": over.get("point"),
                    "dfs_odds_type": over.get("dfs_odds_type") or "standard",
                    "last_change_at": over.get("last_change_at") or "",
                    "line_gap": over.get("line_gap"),
                })

    # De-duplicate: PropLine can retain more than one entry for the same
    # (player, market, point) -- e.g. a stale "standard" snapshot alongside
    # a Demon/Goblin re-price, or vice versa. We tried "most recent timestamp
    # wins" first, but confirmed against the real PrizePicks app on two real
    # cases that recency is NOT reliable -- one case the newer entry was
    # correct, the other the OLDER entry was correct. What held in both
    # cases: the Demon/Goblin-tagged entry matched the live board, and the
    # "standard" one didn't. So: prefer Demon/Goblin over standard regardless
    # of timestamp. Among same-type duplicates, still use most recent.
    # Flagged with "type_conflict" since this is based on only 2 confirmed
    # cases, not a large sample -- worth remaining skeptical of.
    groups = defaultdict(list)
    for leg in pp_lines:
        key = (leg["player"], leg["market"], leg["point"])
        groups[key].append(leg)

    deduped = []
    for key, group in groups.items():
        if len(group) == 1:
            group[0]["type_conflict"] = False
            deduped.append(group[0])
            continue

        types_seen = set(g["dfs_odds_type"] for g in group)
        had_conflict = len(types_seen) > 1
        demon_goblin_entries = [g for g in group if g["dfs_odds_type"] in ("demon", "goblin")]
        candidates = demon_goblin_entries if demon_goblin_entries else group

        chosen = max(candidates, key=lambda g: g["last_change_at"])
        chosen["type_conflict"] = had_conflict
        deduped.append(chosen)

    return deduped


def extract_consensus(event, player, market_key, target_point):
    results = []
    for book in event.get("bookmakers", []):
        if book["key"] not in CONSENSUS_BOOKS:
            continue
        for market in book.get("markets", []):
            if market["key"] != market_key:
                continue
            by_point = defaultdict(dict)
            for outcome in market.get("outcomes", []):
                if outcome.get("description") != player:
                    continue
                by_point[outcome.get("point")][outcome["name"]] = outcome
            if not by_point:
                continue
            chosen_point = target_point if target_point in by_point else None
            is_exact = chosen_point is not None
            if chosen_point is None:
                candidates = [p for p in by_point if p is not None]
                if not candidates or target_point is None:
                    continue
                closest = min(candidates, key=lambda p: abs(p - target_point))
                if abs(closest - target_point) > get_max_gap(market_key):
                    continue
                chosen_point = closest
            sides = by_point[chosen_point]
            over, under = sides.get("Over"), sides.get("Under")
            if not over or not under:
                continue
            novig = devig_two_way(american_to_prob(over["price"]), american_to_prob(under["price"]))
            if not is_exact and novig is not None:
                # Only reachable for GAP_ADJUST_MARKETS (get_max_gap is 0 otherwise):
                # move the book's price to PrizePicks' line instead of using it as-is.
                novig = shift_over_prob(chosen_point, novig, target_point)
            gap = abs(chosen_point - target_point) if target_point is not None else 0.0
            results.append({"book": book["key"], "is_exact_match": is_exact,
                             "gap": gap, "novig_over_prob": novig,
                             "book_point": chosen_point,
                             "over_price": over["price"], "under_price": under["price"]})
    return results


def find_consensus_reference_point(event, player, market_key):
    """The consensus books' own line for this player/market -- a fallback
    reference for computing a goblin/demon leg's deviation when PropLine
    hasn't given us a line_gap for it (see chat: confirmed on a real example
    where 5 separate consensus books all independently listed the same
    point). Takes the median across every consensus book's Over/Under point
    for this player+market (ignoring alt-threshold-style outcomes like
    "15+ Points" that don't carry a numeric point), rather than trusting a
    single book that might be an outlier. Returns None if no consensus book
    has a real point for this player/market at all.
    """
    points = []
    for book in event.get("bookmakers", []):
        if book["key"] not in CONSENSUS_BOOKS:
            continue
        for market in book.get("markets", []):
            if market["key"] != market_key:
                continue
            for outcome in market.get("outcomes", []):
                if outcome.get("description") == player and outcome.get("point") is not None:
                    points.append(outcome["point"])
    if not points:
        return None
    return statistics.median(points)


_THRESHOLD_RE = re.compile(r"(\d+(?:\.\d+)?)\+")


def extract_threshold_ladder(event, player, market_key):
    """Single-sided cumulative 'X+' threshold markets some books publish
    (e.g. "15+ Points", "To Record 10+ Rebounds", "3+ Assists") -- a real,
    book-priced survival curve that often reaches much deeper into the tail
    than a book's own standard Over/Under line does, which is exactly the
    territory a deep demon/goblin line lives in.

    Unlike extract_consensus, these have no listed Under counterpart to
    devig against -- the price is used as-is via american_to_prob, so it
    still carries whatever single-sided vig the book baked in. Treat any
    probability derived from this as meaningfully less reliable than a
    proper two-way devigged number; it's a fallback for when nothing better
    exists, not a replacement for extract_consensus.

    Returns a sorted list of (threshold, probability) tuples, averaging
    across books when more than one publishes the exact same threshold.
    """
    by_threshold = defaultdict(list)
    for book in event.get("bookmakers", []):
        if book["key"] not in CONSENSUS_BOOKS:
            continue
        for market in book.get("markets", []):
            if market["key"] != market_key:
                continue
            for outcome in market.get("outcomes", []):
                if outcome.get("description") != player or outcome.get("point") is not None:
                    continue
                match = _THRESHOLD_RE.search(outcome.get("name") or "")
                if not match:
                    continue
                prob = american_to_prob(outcome.get("price"))
                if prob is not None:
                    by_threshold[float(match.group(1))].append(prob)

    ladder = [(t, sum(ps) / len(ps)) for t, ps in by_threshold.items()]
    ladder.sort(key=lambda p: p[0])
    return ladder


def ladder_extrapolated(ladder, target_point):
    """True when target_point's threshold sits outside the ladder's published
    rungs -- the estimate there is a bound/projection, not a priced number."""
    if not ladder or target_point is None:
        return False
    return not (ladder[0][0] <= target_point + 0.5 <= ladder[-1][0])


def estimate_probability_from_ladder(ladder, target_point):
    """Log-linear interpolate a threshold ladder (see extract_threshold_ladder)
    to estimate the probability of clearing an Over-style point -- e.g. Over
    39.5 needs the stat to reach 40, so this looks up (or blends between) the
    ladder's nearest "40+"-style entries. Returns None if the ladder is empty,
    target_point is unknown, or the ladder can't say anything about it.

    Outside the published rungs there's no price, only a bound, and projecting
    past the curve's end is what produced 98-100% goblins that went 1-for-2:
      - below the lowest rung: P(reach needed) >= P(reach lowest rung), so use
        that rung's probability as-is -- a conservative floor, never a projection up.
      - above the highest rung: project down off the top two rungs (never
        above the top rung's probability); a single rung says nothing -> None.
    Everything is capped at LADDER_MAX_PROB, since these prices still carry
    their one-sided vig, which inflates exactly the near-certain end.
    """
    if not ladder or target_point is None:
        return None
    needed = target_point + 0.5

    if needed <= ladder[0][0]:
        return min(ladder[0][1], LADDER_MAX_PROB)
    if len(ladder) == 1:
        return None
    if needed >= ladder[-1][0]:
        (t0, p0), (t1, p1) = ladder[-2], ladder[-1]
    else:
        t0, p0 = ladder[0]
        for t1, p1 in ladder[1:]:
            if needed <= t1:
                break
            t0, p0 = t1, p1

    if t1 == t0 or p0 <= 0 or p1 <= 0:
        return min(p0, LADDER_MAX_PROB)
    frac = (needed - t0) / (t1 - t0)
    log_p = math.log(p0) + frac * (math.log(p1) - math.log(p0))
    if needed > ladder[-1][0]:
        log_p = min(log_p, math.log(ladder[-1][1]))
    return min(max(math.exp(log_p), 0.0001), LADDER_MAX_PROB)


def poisson_binomial_dist(probs):
    """P(exactly k of len(probs) independent events occur), for k = 0..N,
    given each event's own probability -- NOT assuming they're all equal.
    Needed for Flex entries, which pay out at multiple hit-count tiers
    (e.g. a 4-pick Flex still pays on 3 of 4 hit), unlike Power's true
    all-or-nothing -- grading a Flex entry by P(all hit) alone throws away
    real value from those lower tiers and understates its true EV. Mirrors
    the same DP used client-side in app.js's calcEntry()."""
    dist = [1.0]
    for p in probs:
        new_dist = [0.0] * (len(dist) + 1)
        for k, d in enumerate(dist):
            new_dist[k] += d * (1 - p)
            new_dist[k + 1] += d * p
        dist = new_dist
    return dist


def grade_leg(bar, true_prob_pct):
    margin = true_prob_pct - bar
    if margin < TIER_C_MARGIN:
        tier = "BELOW BAR"
    elif margin < TIER_B_MARGIN:
        tier = "TIER C"
    elif margin < TIER_A_MARGIN:
        tier = "TIER B"
    elif margin < TIER_S_MARGIN:
        tier = "TIER A"
    else:
        tier = "TIER S"
    return margin, tier


def cap_tier(tier, single_book):
    """One book's price is too noisy to call an S/A/B edge -- cap it at C so the
    leg stays visible (margin unchanged) but out of "add every S/A/B leg".
    Mirrored in app.js's tierForMargin for the profit-boost view."""
    return "TIER C" if single_book and tier in SINGLE_BOOK_CAPPED_TIERS else tier


def find_ladder_reference_point(ladder):
    """Where a threshold ladder's own probability curve crosses 50% -- a
    last-resort reference line (see calibrated_bar_for_leg) for when no book
    has a real Over/Under point for this player/market, only the
    single-sided threshold ladder itself (see extract_threshold_ladder).
    This is one layer of estimation further removed from real market data
    than find_consensus_reference_point (which uses an actual
    book-published line), so treat any deviation computed from it with a
    bit more skepticism than usual. Returns None if the ladder is empty.
    """
    if not ladder:
        return None
    if len(ladder) == 1:
        return ladder[0][0]

    # Probability decreases as threshold increases. Find the two adjacent
    # rungs that straddle 50%, extrapolating off the two closest rungs if
    # the whole ladder happens to sit on one side of it.
    if ladder[0][1] <= 0.5:
        (t0, p0), (t1, p1) = ladder[0], ladder[1]
    elif ladder[-1][1] >= 0.5:
        (t0, p0), (t1, p1) = ladder[-2], ladder[-1]
    else:
        t0, p0 = ladder[0]
        for t1, p1 in ladder[1:]:
            if p1 <= 0.5:
                break
            t0, p0 = t1, p1

    if p0 <= 0 or p1 <= 0 or p0 == p1:
        return t0
    frac = (math.log(0.5) - math.log(p0)) / (math.log(p1) - math.log(p0))
    return t0 + frac * (t1 - t0)


def calibrated_bar_for_leg(event, leg, bar, ladder=None):
    """(leg_bar, deviation, assumed_multiplier) for a goblin/demon leg --
    factored out so both a normally-gradeable leg and one with no consensus
    probability data (see build_report) get the same calibration treatment.
    ladder, if given, is a pre-fetched threshold ladder (see
    extract_threshold_ladder) used as a last-resort reference-point source
    when neither line_gap nor a real consensus Over/Under line is available.
    """
    if leg.get("line_gap") is not None:
        deviation = abs(leg["line_gap"])
        if leg["dfs_odds_type"] == "goblin":
            deviation = -deviation
    else:
        # PropLine didn't give us a line_gap for this one -- fall back to the
        # consensus books' own line as the reference instead of leaving it
        # ungraded-for-type. See find_consensus_reference_point.
        reference_point = find_consensus_reference_point(event, leg["player"], leg["market"])
        if reference_point is None and ladder:
            reference_point = find_ladder_reference_point(ladder)
        deviation = (leg["point"] - reference_point
                     if reference_point is not None and leg["point"] is not None else None)

    assumed_multiplier = None
    leg_bar = bar
    if deviation is not None:
        assumed_multiplier = estimate_multiplier(
            leg["market"], leg["dfs_odds_type"], deviation, STANDARD_2PICK_LEG_MULTIPLIER)
        if assumed_multiplier:
            leg_bar = 100.0 / assumed_multiplier
    return leg_bar, deviation, assumed_multiplier


def _grade_leg(event, leg, bar):
    """Grade one leg -- {player, market, point, dfs_odds_type, line_gap,
    type_conflict} -- against this event's consensus books. Returns a row
    dict, or None if there's nothing gradeable to show (no consensus data,
    no threshold-ladder fallback, and not a goblin/demon leg). Shared by
    build_report (fed real PrizePicks lines) and grade_manual_leg (fed a
    hand-entered line, e.g. a promo/discount pick PropLine doesn't carry)."""
    is_demon_or_goblin_leg = leg["dfs_odds_type"] in ("goblin", "demon")
    # A "discount" leg (e.g. a Taco Tuesday promo) moves the line far below
    # market like a goblin -- so it needs the same one-sided threshold-ladder
    # fallback -- but it pays PrizePicks' full STANDARD multiplier, not a
    # reduced goblin one. So it shares goblin/demon's fallback eligibility and
    # forced "More" side below, but must never touch calibrated_bar_for_leg
    # (that's gated on is_demon_or_goblin_leg specifically, further down).
    is_one_sided_leg = leg["dfs_odds_type"] in ("goblin", "demon", "discount")
    consensus = extract_consensus(event, leg["player"], leg["market"], leg["point"])
    probs = [c["novig_over_prob"] for c in consensus if c["novig_over_prob"] is not None]

    # from_ladder stays None unless we fall back to the single-sided
    # threshold-ladder estimate below -- used to flag the resulting row
    # as meaningfully less certain than a real two-way devigged number.
    # ladder itself (not just from_ladder) is also reused below as a
    # last-resort reference-point source for the calibrated bar.
    #
    # Tried for EVERY leg type when there's no direct two-way match, not just
    # goblin/demon/discount -- confirmed on real WNBA data that consensus
    # books can carry a player/market ONLY as cumulative "X+" threshold
    # outcomes (no numeric `point` on the Over/Under at all), which
    # extract_consensus() correctly skips since there's no line to match
    # against. That left every "standard" PrizePicks leg for those players
    # silently dropped even though real, market-derived probability data for
    # them existed in ladder form the whole time. is_one_sided_leg still
    # governs which SIDE a leg grades on below -- this only widens which
    # types get to try the ladder as a data source.
    ladder = None
    from_ladder = None
    if not probs:
        ladder = extract_threshold_ladder(event, leg["player"], leg["market"])
        from_ladder = estimate_probability_from_ladder(ladder, leg["point"])

    if not probs and from_ladder is None:
        # No consensus book has a safe match at this leg's own point, and no
        # threshold ladder covers it either -- there's no true hit
        # probability to compute for ANY leg type, so don't fabricate one.
        # Still show the leg with whatever calibrated multiplier we can find
        # (line_gap or the consensus books' own reference line) instead of
        # letting it silently vanish from the results -- this used to only
        # apply to goblin/demon, which just meant a standard/discount leg in
        # this same no-data situation disappeared instead of showing "NO
        # DATA" like its goblin/demon siblings did.
        leg_bar, deviation, assumed_multiplier = calibrated_bar_for_leg(event, leg, bar, ladder)
        return {
            "player": leg["player"], "market": leg["market"], "point": leg["point"],
            "dfs_type": leg["dfs_odds_type"], "books": [],
            "type_conflict": leg.get("type_conflict", False),
            "side": "More",
            "consensus_pct": None,
            "spread_pct": None,
            "single_book": False, "bar": round(leg_bar, 1), "margin": None,
            "tier": "NO DATA", "estimated": False, "gap": None,
            "deviation": deviation, "assumed_multiplier": round(assumed_multiplier, 2) if assumed_multiplier else None,
            "estimate_type": "NO_BOOK", "whole_number": leg["point"] is not None and float(leg["point"]) % 1 == 0,
            "book_point": None, "over_price": None, "under_price": None,
            "tier_capped": False, "book_prices": [],
        }

    if from_ladder is not None:
        over_pct = from_ladder * 100
        under_pct = 100.0 - over_pct
        spread_pct = None
        single_book = False
        any_estimate = True
        max_gap = 0.0
        books_used = ["threshold ladder (pooled)"]
    else:
        # Median, not mean: one soft or stale book can't drag the consensus,
        # and it needs no opinion on which books are sharp. Same as the mean
        # for 1-2 books. Revisit with weighting once leg_prices.jsonl (see
        # excel_logging.py) has enough logged legs to test it on.
        over_pct = statistics.median(probs) * 100
        under_pct = 100.0 - over_pct
        spread_pct = (max(probs) - min(probs)) * 100 if len(probs) > 1 else None
        single_book = len(probs) < 2
        any_estimate = any(not c["is_exact_match"] for c in consensus)
        max_gap = max((c["gap"] for c in consensus), default=0.0)
        books_used = [c["book"] for c in consensus]

    # Demon, Goblin, and discount lines can ONLY be picked as More/Over on
    # PrizePicks -- there's no Less option for them. So unlike standard lines
    # (where we grade whichever side actually clears the bar), these are
    # always graded on Over, even in the rare case Under's probability is
    # higher -- that just means the pick itself is a bad one, not that
    # there's a Less version of it to fall back to.
    if is_one_sided_leg:
        side, true_pct = "More", over_pct
    elif over_pct >= under_pct:
        side, true_pct = "More", over_pct
    else:
        side, true_pct = "Less", under_pct

    # Goblins pay less than a standard line (safer, lower multiplier) and
    # demons pay more (riskier, higher multiplier) -- grading either one
    # against the flat standard-entry bar makes goblins look inflated and
    # demons look suppressed. Where we have a calibrated multiplier for
    # this market (see goblin_demon_calibration.py), grade the leg against
    # its own implied break-even instead of the flat bar. Markets without
    # calibration data yet keep the old flat-bar behavior.
    leg_bar, deviation, assumed_multiplier = (
        calibrated_bar_for_leg(event, leg, bar, ladder) if is_demon_or_goblin_leg else (bar, None, None))

    if is_demon_or_goblin_leg and assumed_multiplier is None:
        # No calibration data yet for this market/deviation -- calibrated_bar_for_leg
        # falls back to the flat standard bar in that case, but grading against it
        # would silently assume a payout we don't actually know (a real goblin might
        # pay far less than what the flat bar implies, a demon far more). Leave it
        # untiered instead of fabricating a grade. true_pct is still real and shown,
        # so it still sorts sensibly -- see build_report's sort key below.
        leg_bar, margin, tier = None, None, "UNKNOWN"
    else:
        margin, tier = grade_leg(leg_bar, true_pct)

    tier_capped = cap_tier(tier, single_book) != tier
    tier = cap_tier(tier, single_book)

    # Estimate-type taxonomy for spreadsheet logging (see PrizePicks_Model_Tracking.xlsx
    # Legend). NOTE: we do NOT do push modeling -- whole-number lines are tagged by
    # their actual matching method (exact/estimated), not auto-labeled PUSH_FITTED,
    # since claiming a push model we haven't built would misrepresent the methodology.
    # (NO_BOOK is used for the no-consensus-data branch above, not reachable here.)
    if from_ladder is not None:
        estimate_type = "THRESHOLD_LADDER"
    elif is_demon_or_goblin_leg and any_estimate:
        estimate_type = "GOBLIN_FIT"
    elif any_estimate:
        estimate_type = "GAP_ADJUSTED"  # Poisson-shifted from a book line up to GAP_ADJUST_MAX away
    else:
        estimate_type = "EXACT_MATCH"
    whole_number = leg["point"] is not None and float(leg["point"]) % 1 == 0

    # Representative book price/point for logging -- prefer an exact match if
    # one exists among the books used, else just take the first. Not
    # meaningful for a pooled threshold-ladder estimate (no single
    # matching book/price), so left blank there.
    if from_ladder is not None:
        book_point, over_price, under_price = None, None, None
    else:
        exact_matches = [c for c in consensus if c["is_exact_match"]]
        rep = exact_matches[0] if exact_matches else consensus[0]
        book_point, over_price, under_price = rep["book_point"], rep["over_price"], rep["under_price"]

    return {
        "player": leg["player"], "market": leg["market"], "point": leg["point"],
        "dfs_type": leg["dfs_odds_type"], "books": books_used,
        "type_conflict": leg.get("type_conflict", False),
        "side": side,
        "consensus_pct": round(true_pct, 1),
        "spread_pct": round(spread_pct, 1) if spread_pct is not None else None,
        "single_book": single_book,
        "bar": round(leg_bar, 1) if leg_bar is not None else None,
        "margin": round(margin, 1) if margin is not None else None,
        "tier": tier, "estimated": any_estimate, "gap": round(max_gap, 1),
        "deviation": deviation, "assumed_multiplier": round(assumed_multiplier, 2) if assumed_multiplier else None,
        "estimate_type": estimate_type, "whole_number": whole_number,
        "ladder_extrapolated": from_ladder is not None and ladder_extrapolated(ladder, leg["point"]),
        "tier_capped": tier_capped,
        "book_point": book_point, "over_price": over_price, "under_price": under_price,
        # Every book's own price behind this leg, [book, point, over, under] --
        # compact on purpose (rows sit in browser storage). Logged to
        # leg_prices.jsonl so book weighting/de-vig changes can be tested later.
        "book_prices": [[c["book"], c["book_point"], c["over_price"], c["under_price"]] for c in consensus]
                       if from_ladder is None else [],
    }


# Sort priority, best to worst: a real graded tier (S/A/B/C, ranked by
# margin) > UNKNOWN (goblin/demon with no calibration data -- a real
# probability, just no verdict on its unknown payout) > BELOW BAR (a real
# grade that's confirmed to miss its bar) > NO DATA (no probability at all).
# UNKNOWN sits above BELOW BAR deliberately: "we don't know" is more
# promising than "we know this misses" -- see chat.
_TIER_BUCKET = {"TIER S": 3, "TIER A": 3, "TIER B": 3, "TIER C": 3, "UNKNOWN": 2, "BELOW BAR": 1, "NO DATA": 0}
_TIER_RANK = {"TIER S": 4, "TIER A": 3, "TIER B": 2, "TIER C": 1}


def row_sort_key(r):
    """Shared by build_report and scan_slate so both sort identically."""
    bucket = _TIER_BUCKET.get(r["tier"], 0)
    if bucket == 3:
        rank = (_TIER_RANK[r["tier"]], r["margin"])  # tier first: a capped single-book C can have a big margin
    elif bucket == 2:
        rank = (0, r["consensus_pct"] if r["consensus_pct"] is not None else -1)
    elif bucket == 1:
        rank = (0, r["margin"] if r["margin"] is not None else -1)
    else:
        rank = (0, 0)
    return (bucket, rank)


def build_report(event, bar, board="prizepicks"):
    pp_lines = extract_pp_lines(event, board=board)
    rows = [row for row in (_grade_leg(event, leg, bar) for leg in pp_lines) if row is not None]
    rows.sort(key=row_sort_key, reverse=True)
    return rows, bar


def grade_manual_leg(event, player, market, point, dfs_type, bar):
    """Grade a hand-entered line that doesn't come from PropLine's own feed --
    e.g. a PrizePicks promo/discount pick ("Taco Tuesday" style), which isn't
    exposed through the API. Reuses the exact same consensus-book grading as
    a normal scanned leg; only the leg's origin differs. Returns a row dict
    (see _grade_leg), or None if there's no consensus/ladder data to grade
    against at all."""
    leg = {
        "player": player, "market": market, "point": point,
        "dfs_odds_type": dfs_type, "line_gap": None, "type_conflict": False,
    }
    return _grade_leg(event, leg, bar)
