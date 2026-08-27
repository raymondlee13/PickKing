"""Edge-grading logic: consensus de-vigging, tiering, and report building.
Pure data transforms -- no network calls (see propline_api.py for those)."""

from collections import defaultdict

from goblin_demon_calibration import estimate_multiplier

DFS_BOOKS = {"prizepicks", "underdog", "sleeper", "dabble"}
CONSENSUS_BOOKS = {"draftkings", "fanduel", "betmgm", "caesars", "betrivers",
                    "pinnacle", "bovada", "unibet"}

POWER_PLAY_BARS = {2: 57.7, 3: 55.0, 4: 56.0, 5: 55.0, 6: 55.0}
# Per-leg break-even for Flex, solved via real multi-tier EV math (see chat) --
# assumes equal probability across legs, same caveat as the reference chart.
# Flex has no 2-pick option.
FLEX_BARS = {3: 57.7, 4: 55.0, 5: 54.3, 6: 54.2}
TIER_A_MARGIN = 4.0
TIER_B_MARGIN = 1.5
# The standard leg's own fair multiplier for a 2-pick Power entry, derived
# from POWER_PLAY_BARS[2] -- every goblin/demon calibration example so far
# was captured as a real 2-pick entry (one standard leg + one alt leg), so
# this is what estimate_multiplier divides that observed total by to isolate
# the alt leg's own contribution. See goblin_demon_calibration.py.
STANDARD_2PICK_LEG_MULTIPLIER = 100.0 / POWER_PLAY_BARS[2]
# Safety default flipped after the WNBA assists bug: markets require an EXACT
# line match unless explicitly whitelisted below as safe to estimate within
# a small gap. Unconfirmed/new sports (like MLB) inherit this safe default
# automatically -- nothing gets graded off a fudged number by mistake.
WIDE_MARKETS_MAX_GAP = {
    "player_points": 1.0,
    "player_rebounds": 1.0,
    "player_points_rebounds_assists": 1.0,
}
DEFAULT_MAX_GAP = 0.0  # exact match only, unless whitelisted above

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

MARKETS_BY_SPORT = {
    "basketball_wnba": BASKETBALL_MARKETS,
    "basketball_nba": BASKETBALL_MARKETS,
    "baseball_mlb": MLB_MARKETS,
}


def get_max_gap(market_key):
    return WIDE_MARKETS_MAX_GAP.get(market_key, DEFAULT_MAX_GAP)


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


def extract_raw_prizepicks(event, board="prizepicks"):
    """Raw, unprocessed markets/outcomes for one platform -- used by the
    in-app raw data viewer so debugging doesn't require Command Prompt."""
    for book in event.get("bookmakers", []):
        if book["key"] == board:
            return book.get("markets", [])
    return []


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
            gap = abs(chosen_point - target_point) if target_point is not None else 0.0
            results.append({"book": book["key"], "is_exact_match": is_exact,
                             "gap": gap, "novig_over_prob": novig,
                             "book_point": chosen_point,
                             "over_price": over["price"], "under_price": under["price"]})
    return results


def grade_leg(bar, true_prob_pct):
    margin = true_prob_pct - bar
    if margin < TIER_B_MARGIN:
        tier = "BELOW BAR"
    elif margin < TIER_A_MARGIN:
        tier = "TIER B"
    else:
        tier = "TIER A"
    return margin, tier


def build_report(event, bar, board="prizepicks"):
    pp_lines = extract_pp_lines(event, board=board)
    rows = []
    for leg in pp_lines:
        consensus = extract_consensus(event, leg["player"], leg["market"], leg["point"])
        if not consensus:
            continue
        probs = [c["novig_over_prob"] for c in consensus if c["novig_over_prob"] is not None]
        if not probs:
            continue
        over_pct = (sum(probs) / len(probs)) * 100
        under_pct = 100.0 - over_pct
        # Demon and Goblin lines can ONLY be picked as More/Over on PrizePicks --
        # there's no Less option for them. So unlike standard lines (where we grade
        # whichever side actually clears the bar), Demon/Goblin legs are always
        # graded on Over, even in the rare case Under's probability is higher --
        # that just means the Demon/Goblin pick itself is a bad one, not that
        # there's a Less version of it to fall back to.
        is_demon_or_goblin_leg = leg["dfs_odds_type"] in ("goblin", "demon")
        if is_demon_or_goblin_leg:
            side, true_pct = "More", over_pct
        elif over_pct >= under_pct:
            side, true_pct = "More", over_pct
        else:
            side, true_pct = "Less", under_pct
        spread_pct = (max(probs) - min(probs)) * 100 if len(probs) > 1 else None
        single_book = len(probs) < 2
        any_estimate = any(not c["is_exact_match"] for c in consensus)
        max_gap = max((c["gap"] for c in consensus), default=0.0)

        # Goblins pay less than a standard line (safer, lower multiplier) and
        # demons pay more (riskier, higher multiplier) -- grading either one
        # against the flat standard-entry bar makes goblins look inflated and
        # demons look suppressed. Where we have a calibrated multiplier for
        # this market (see goblin_demon_calibration.py), grade the leg against
        # its own implied break-even instead of the flat bar. Markets without
        # calibration data yet keep the old flat-bar behavior.
        leg_bar = bar
        deviation = None
        assumed_multiplier = None
        if is_demon_or_goblin_leg and leg.get("line_gap") is not None:
            deviation = abs(leg["line_gap"])
            if leg["dfs_odds_type"] == "goblin":
                deviation = -deviation
            assumed_multiplier = estimate_multiplier(
                leg["market"], leg["dfs_odds_type"], deviation, STANDARD_2PICK_LEG_MULTIPLIER)
            if assumed_multiplier:
                leg_bar = 100.0 / assumed_multiplier

        margin, tier = grade_leg(leg_bar, true_pct)

        # Estimate-type taxonomy for spreadsheet logging (see PrizePicks_Model_Tracking.xlsx
        # Legend). NOTE: we do NOT do push modeling -- whole-number lines are tagged by
        # their actual matching method (exact/estimated), not auto-labeled PUSH_FITTED,
        # since claiming a push model we haven't built would misrepresent the methodology.
        # NO_BOOK never occurs here since a row can't exist without at least one book match.
        is_demon_or_goblin = leg["dfs_odds_type"] in ("goblin", "demon")
        if is_demon_or_goblin and any_estimate:
            estimate_type = "GOBLIN_FIT"
        elif any_estimate:
            estimate_type = "ALT_ESTIMATED"
        else:
            estimate_type = "EXACT_MATCH"
        whole_number = leg["point"] is not None and float(leg["point"]) % 1 == 0

        # Representative book price/point for logging -- prefer an exact match if
        # one exists among the books used, else just take the first.
        exact_matches = [c for c in consensus if c["is_exact_match"]]
        rep = exact_matches[0] if exact_matches else consensus[0]

        rows.append({
            "player": leg["player"], "market": leg["market"], "point": leg["point"],
            "dfs_type": leg["dfs_odds_type"], "books": [c["book"] for c in consensus],
            "type_conflict": leg.get("type_conflict", False),
            "side": side,
            "consensus_pct": round(true_pct, 1),
            "spread_pct": round(spread_pct, 1) if spread_pct is not None else None,
            "single_book": single_book, "bar": round(leg_bar, 1), "margin": round(margin, 1),
            "tier": tier, "estimated": any_estimate, "gap": round(max_gap, 1),
            "deviation": deviation, "assumed_multiplier": round(assumed_multiplier, 2) if assumed_multiplier else None,
            "estimate_type": estimate_type, "whole_number": whole_number,
            "book_point": rep["book_point"], "over_price": rep["over_price"], "under_price": rep["under_price"],
        })
    rows.sort(key=lambda r: r["margin"], reverse=True)
    return rows, bar
