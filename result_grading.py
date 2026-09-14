"""Auto-grading logged picks against real box scores from PropLine's own
/events/{id}/stats endpoint -- confirmed to return per-player stat lines
(receiving_yards, hits, home_runs, etc.), not just team scores, for both NFL
and MLB against real completed games (see chat). Since it's the same
PropLine player-name convention already used for odds, no fuzzy name
matching against a separate data source is needed -- the odds feed's player
name should already match the stats feed's player name for the same game.
"""

import re

from propline_api import fetch_event_stats

# market_key -> PropLine stat_type, confirmed against real completed games.
STAT_KEY_MAP = {
    "americanfootball_nfl": {
        "player_pass_yds": "passing_yards",
        "player_pass_tds": "passing_tds",
        "player_pass_completions": "passing_completions",
        "player_pass_attempts": "passing_attempts",
        "player_pass_interceptions": "interceptions",
        "player_rush_yds": "rushing_yards",
        "player_rush_attempts": "rushing_attempts",
        "player_receptions": "receptions",
        "player_reception_yds": "receiving_yards",
        "player_pass_rush_reception_yds": "rush_reception_yds",
        "player_kicking_points": "kicking_points",
        "player_field_goals": "field_goals_made",
        "player_anytime_td": "anytime_td",
    },
    "baseball_mlb": {
        "batter_hits": "hits",
        "batter_home_runs": "home_runs",
        "batter_rbis": "rbis",
        "batter_hits_runs_rbis": "hits_runs_rbis",
        "batter_runs_scored": "runs",
        "batter_stolen_bases": "stolen_bases",
        "batter_total_bases": "total_bases",
        "pitcher_strikeouts": "strikeouts",
        "pitcher_hits_allowed": "hits_allowed",
        "pitcher_walks": "walks",
        "pitcher_outs": "outs",
    },
    # NOT yet confirmed against a real completed NBA/WNBA game (none were
    # available to check) -- best guess following the same naming pattern
    # PropLine uses for NFL/MLB. Verify before trusting these two.
    "basketball_nba": {
        "player_points": "points",
        "player_rebounds": "rebounds",
        "player_assists": "assists",
        "player_threes": "three_pointers_made",
        "player_blocks": "blocks",
        "player_steals": "steals",
    },
}
STAT_KEY_MAP["basketball_wnba"] = STAT_KEY_MAP["basketball_nba"]

# Markets that aren't a single PropLine stat_type but a sum of a few --
# confirmed hits_runs_rbis IS a direct stat for MLB, so only PRA needs this.
COMBINED_STAT_COMPONENTS = {
    "player_points_rebounds_assists": ["points", "rebounds", "assists"],
}

# The [pk:...] tag appended to a logged leg's Note column (see excel_logging.py)
# so a later "check results" pass can re-fetch the exact game a pick came from
# directly, instead of re-matching team names/dates against the API.
_TAG_RE = re.compile(r"\[pk:sport=([^,\]]*),event=([^,\]]*),market=([^\]]*)\]")


def build_tag(sport, event_id, market):
    return f"[pk:sport={sport},event={event_id},market={market}]"


def parse_tag(note):
    m = _TAG_RE.search(note or "")
    if not m:
        return None
    sport, event_id, market = m.groups()
    if not sport or not event_id or not market:
        return None
    return {"sport": sport, "event_id": event_id, "market": market}


def _lookup_stat_value(market_key, sport_key, stats, player_name):
    by_stat = {}
    for s in stats:
        if s.get("player_name") == player_name:
            by_stat[s.get("stat_type")] = s.get("stat_value")

    components = COMBINED_STAT_COMPONENTS.get(market_key)
    if components:
        values = [by_stat.get(c) for c in components]
        if any(v is None for v in values):
            return None
        return sum(values)

    stat_type = STAT_KEY_MAP.get(sport_key, {}).get(market_key)
    if not stat_type:
        return None
    return by_stat.get(stat_type)


def grade_pick(market_key, sport_key, stats, player_name, point, side):
    """"W"/"L"/"PUSH", or None if this can't be graded yet (player not found
    in the box score, or this market isn't mapped to a known stat_type)."""
    value = _lookup_stat_value(market_key, sport_key, stats, player_name)
    if value is None or point is None:
        return None
    if side == "More":
        if value > point:
            return "W"
        if value < point:
            return "L"
        return "PUSH"
    else:
        if value < point:
            return "W"
        if value > point:
            return "L"
        return "PUSH"


def check_result(sport, event_id, market, player, point, side, api_key, stats_cache=None):
    """Fetch the event's box score and grade one pick against it. Returns
    (status, result, actual_value):
      status "final" + result "W"/"L"/"PUSH" -- graded
      status "final" + result None -- game's over but player/market not found
      status "upcoming"/other -- game hasn't finished yet, nothing to grade

    stats_cache, if given, is a dict this call reads/writes keyed by
    (sport, event_id) -- pass the same dict across many calls (e.g. checking
    every pending leg in a workbook) so legs from the same game only trigger
    one API request instead of one per leg.
    """
    cache_key = (sport, event_id)
    if stats_cache is not None and cache_key in stats_cache:
        data = stats_cache[cache_key]
    else:
        data = fetch_event_stats(sport, event_id, api_key)
        if stats_cache is not None:
            stats_cache[cache_key] = data

    status = data.get("status")
    if status != "final":
        return status, None, None
    stats = data.get("stats", [])
    result = grade_pick(market, sport, stats, player, point, side)
    actual_value = _lookup_stat_value(market, sport, stats, player)
    return status, result, actual_value
