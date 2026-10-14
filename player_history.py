"""Recent player form from ESPN's free public site API -- display-only context.

Hit rates ("cleared this line in 7 of the last 10") and a simple projection,
plus the per-game values the ticket uses to show how often two same-game legs
hit together. NEVER feeds consensus_pct/bar/margin/tier: grading stays purely
market-derived (see PRODUCT.md), and calibration_report can later show whether
any of this actually predicts anything.

ESPN's site API is unofficial and undocumented -- it can change or block
without warning, so every failure here degrades to "no history", never an
error in grading. Finished games never change, so each box score is fetched
once and kept in espn_cache/ (gitignored); schedules and scoreboards are only
cached in memory for a short while.
"""

import datetime
import json
import os
import re
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "espn_cache")
ESPN = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_PATH = {
    "basketball_nba": "basketball/nba", "basketball_wnba": "basketball/wnba",
    "americanfootball_nfl": "football/nfl", "baseball_mlb": "baseball/mlb",
}
GAMES = 10             # how many recent games per player
RECENCY_WEIGHT = 0.85  # projection weight per game back: newest 1.0, then 0.85, 0.72, ...
FETCH_WORKERS = 4      # box scores fetched at once -- polite to an unofficial API
MEMORY_TTL = 30 * 60   # schedules/scoreboards: re-fetch after 30 minutes
_memory = {}           # url -> (fetched_at, json)

_SUFFIX_RE = re.compile(r"(jr|sr|ii|iii|iv)$")


def name_key(name):
    """Name compared loosely: no accents, case, punctuation, spacing or Jr./III
    suffix -- the books, PrizePicks and ESPN each spell names their own way."""
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    key = "".join(ch for ch in plain.lower() if ch.isalnum())
    return _SUFFIX_RE.sub("", key) or key


def _get(url, ttl=None):
    """ESPN JSON. ttl caches it in memory for that many seconds."""
    hit = _memory.get(url)
    if ttl and hit and time.time() - hit[0] < ttl:
        return hit[1]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if ttl:
        _memory[url] = (time.time(), data)
    return data


# ---- Box scores -> PickKing market values --------------------------------

def _num(text, part=0):
    """'11' -> 11.0; '2-4' / '19/34' -> the part'th number; '' / '--' -> None."""
    pieces = re.split(r"[-/]", str(text or "").strip())
    try:
        return float(pieces[part])
    except (ValueError, IndexError):
        return None


def _outs(innings):
    """Pitcher innings '5.2' (5 full + 2 outs) -> 17 outs."""
    try:
        full, _, part = str(innings).partition(".")
        return float(int(full) * 3 + int(part or 0))
    except ValueError:
        return None


def _total(*values):
    return None if all(v is None for v in values) else sum(v or 0.0 for v in values)


# market -> how to read it from a player's raw box-score stats ({"category.key": "text"}).
MARKETS = {
    "basketball": {
        "player_points": lambda s: _num(s.get(".points")),
        "player_rebounds": lambda s: _num(s.get(".rebounds")),
        "player_assists": lambda s: _num(s.get(".assists")),
        "player_threes": lambda s: _num(s.get(".threePointFieldGoalsMade-threePointFieldGoalsAttempted")),
        "player_blocks": lambda s: _num(s.get(".blocks")),
        "player_steals": lambda s: _num(s.get(".steals")),
        "player_points_rebounds_assists": lambda s: _total(
            _num(s.get(".points")), _num(s.get(".rebounds")), _num(s.get(".assists"))),
        "player_points_rebounds": lambda s: _total(_num(s.get(".points")), _num(s.get(".rebounds"))),
        "player_points_assists": lambda s: _total(_num(s.get(".points")), _num(s.get(".assists"))),
        "player_rebounds_assists": lambda s: _total(_num(s.get(".rebounds")), _num(s.get(".assists"))),
        "player_turnovers": lambda s: _num(s.get(".turnovers")),
    },
    "americanfootball_nfl": {
        "player_pass_yds": lambda s: _num(s.get("passing.passingYards")),
        "player_pass_tds": lambda s: _num(s.get("passing.passingTouchdowns")),
        "player_pass_completions": lambda s: _num(s.get("passing.completions/passingAttempts"), 0),
        "player_pass_attempts": lambda s: _num(s.get("passing.completions/passingAttempts"), 1),
        "player_pass_interceptions": lambda s: _num(s.get("passing.interceptions")),
        "player_rush_yds": lambda s: _num(s.get("rushing.rushingYards")),
        "player_rush_attempts": lambda s: _num(s.get("rushing.rushingAttempts")),
        "player_receptions": lambda s: _num(s.get("receiving.receptions")),
        "player_reception_yds": lambda s: _num(s.get("receiving.receivingYards")),
        "player_pass_rush_reception_yds": lambda s: _total(
            _num(s.get("passing.passingYards")), _num(s.get("rushing.rushingYards")),
            _num(s.get("receiving.receivingYards"))),
        "player_kicking_points": lambda s: _num(s.get("kicking.totalKickingPoints")),
        "player_field_goals": lambda s: _num(s.get("kicking.fieldGoalsMade/fieldGoalAttempts"), 0),
        "player_anytime_td": lambda s: _total(
            _num(s.get("rushing.rushingTouchdowns")), _num(s.get("receiving.receivingTouchdowns"))),
        "player_rush_reception_yds": lambda s: _total(
            _num(s.get("rushing.rushingYards")), _num(s.get("receiving.receivingYards"))),
        "player_pass_rush_yds": lambda s: _total(
            _num(s.get("passing.passingYards")), _num(s.get("rushing.rushingYards"))),
        "player_reception_longest": lambda s: _num(s.get("receiving.longReception")),
        "player_rush_longest": lambda s: _num(s.get("rushing.longRushing")),
    },
    "baseball_mlb": {
        # ESPN's box score has no stolen bases, total bases, singles or doubles -- no history for those.
        "batter_hits": lambda s: _num(s.get("batting.hits")),
        "batter_home_runs": lambda s: _num(s.get("batting.homeRuns")),
        "batter_rbis": lambda s: _num(s.get("batting.RBIs")),
        "batter_runs_scored": lambda s: _num(s.get("batting.runs")),
        "batter_hits_runs_rbis": lambda s: _total(
            _num(s.get("batting.hits")), _num(s.get("batting.runs")), _num(s.get("batting.RBIs"))),
        "batter_walks": lambda s: _num(s.get("batting.walks")),
        "pitcher_earned_runs": lambda s: _num(s.get("pitching.earnedRuns")),
        "pitcher_strikeouts": lambda s: _num(s.get("pitching.strikeouts")),
        "pitcher_hits_allowed": lambda s: _num(s.get("pitching.hits")),
        "pitcher_walks": lambda s: _num(s.get("pitching.walks")),
        "pitcher_outs": lambda s: _outs(s.get("pitching.fullInnings.partInnings")),
    },
}
MARKETS["basketball_nba"] = MARKETS["basketball_wnba"] = MARKETS.pop("basketball")


def market_values(sport, raw):
    """A player's raw ESPN stats ({"category.key": text}) -> {market: value}."""
    values = {m: read(raw) for m, read in MARKETS[sport].items()}
    if sport == "americanfootball_nfl":
        # ESPN only lists a player in the receiving/rushing/... table if he
        # recorded one -- he played, so a missing table means 0, not unknown.
        values = {m: 0.0 if v is None else v for m, v in values.items()}
    return {m: v for m, v in values.items() if v is not None}


def parse_box_score(sport, summary):
    """ESPN game summary -> {"date": iso, "players": {espn name: {"team": id,
    "stats": {market: value}}}}. Players who didn't play are left out."""
    return _with_markets(sport, raw_box_score(sport, summary))


def _with_markets(sport, box):
    return {"date": box["date"], "players": {
        name: {"team": p["team"], "stats": market_values(sport, p["raw"])} for name, p in box["players"].items()}}


def raw_box_score(sport, summary):
    """ESPN game summary -> {"date", "players": {espn name: {"team": id, "raw":
    {"category.key": text}}}} -- ESPN's stats as-is. This is what gets cached,
    so a market added later still works on games saved before it existed."""
    players = {}
    for team in (summary.get("boxscore") or {}).get("players", []):
        team_id = str(team.get("team", {}).get("id", ""))
        raw = {}  # athlete id -> (name, {"category.key": text})
        for cat in team.get("statistics", []):
            keys = cat.get("keys") or []
            name = cat.get("name") or ""
            if sport == "baseball_mlb" and not name:  # MLB's two tables are unnamed
                name = "pitching" if "fullInnings.partInnings" in keys else "batting"
            for a in cat.get("athletes", []):
                if a.get("didNotPlay") or not a.get("stats"):
                    continue
                athlete = a.get("athlete", {})
                entry = raw.setdefault(athlete.get("id"), (athlete.get("displayName", ""), {}))
                entry[1].update({f"{name}.{k}": v for k, v in zip(keys, a["stats"])})
        for display_name, stats in raw.values():
            players[display_name] = {"team": team_id, "raw": stats}
    date = ((summary.get("header") or {}).get("competitions") or [{}])[0].get("date", "")
    return {"date": date, "players": players}


def _box_score(sport, event_id):
    """Box score for a FINISHED ESPN game ({"date", "players": {name: {"team",
    "stats": {market: value}}}}), with ESPN's raw stats cached on disk."""
    path = os.path.join(CACHE_DIR, sport, f"{event_id}.json")
    try:
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
        if all("raw" in p for p in cached["players"].values()):  # older files held converted stats only
            return _with_markets(sport, cached)
    except (OSError, ValueError, KeyError):
        pass
    raw = raw_box_score(sport, _get(f"{ESPN}/{ESPN_PATH[sport]}/summary?event={event_id}"))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f)
        os.replace(tmp, path)
    except OSError:
        pass  # can't cache -- still usable this time
    return _with_markets(sport, raw)


# ---- Finding the game and each team's recent games -----------------------

def _find_espn_game(sport, home_team, away_team, commence_time):
    """{"home": espn team id, "away": ...} for this matchup, via ESPN's
    scoreboard around the game's date (UTC vs local can shift it a day)."""
    want = {name_key(home_team), name_key(away_team)}
    day = datetime.datetime.fromisoformat(commence_time.replace("Z", "+00:00")).date()
    for offset in (0, -1, 1):
        stamp = (day + datetime.timedelta(days=offset)).strftime("%Y%m%d")
        board = _get(f"{ESPN}/{ESPN_PATH[sport]}/scoreboard?dates={stamp}", ttl=MEMORY_TTL)
        for event in board.get("events", []):
            teams = event.get("competitions", [{}])[0].get("competitors", [])
            names = {name_key(t.get("team", {}).get("displayName")): t for t in teams}
            if want <= set(names):
                return {side: str(names[name_key(team)]["team"]["id"])
                        for side, team in (("home", home_team), ("away", away_team))}
    return None


def _recent_events(sport, team_id, before, n=GAMES):
    """ESPN ids of this team's last n finished regular-season/playoff games
    before `before` -- reaching into last season when this one is too young."""
    events = []
    url = f"{ESPN}/{ESPN_PATH[sport]}/teams/{team_id}/schedule"
    schedule = _get(url, ttl=MEMORY_TTL)
    year = (schedule.get("requestedSeason") or schedule.get("season") or {}).get("year")
    for sched in (schedule, _get(f"{url}?season={year - 1}", ttl=MEMORY_TTL) if year else None):
        if not sched:
            continue
        for e in sched.get("events", []):
            comp = (e.get("competitions") or [{}])[0]
            final = comp.get("status", {}).get("type", {}).get("completed")
            if final and (e.get("seasonType") or {}).get("type") in (2, 3) and e.get("date", "") < before:
                events.append((e["date"], str(e["id"])))
        if len({eid for _, eid in events}) >= n:
            break
    return [eid for _, eid in sorted(set(events), reverse=True)[:n]]


def projection(values):
    """Recency-weighted average (newest counts most) -- a simple, honest
    baseline, not a model. None if there's nothing to average."""
    pairs = [(RECENCY_WEIGHT ** i, v) for i, v in enumerate(values) if v is not None]
    if not pairs:
        return None
    return round(sum(w * v for w, v in pairs) / sum(w for w, _ in pairs), 1)


def recent_form(sport, game, players):
    """Recent games for the requested players of one PropLine game.

    game: {"home_team", "away_team", "commence_time"}; players: {name: [markets]}.
    Returns {name: {"events": [espn ids, newest first], "values": {market: [...]},
    "proj": {market: x}}} -- values line up with events (None = didn't record
    that stat). Players ESPN can't find are left out."""
    if sport not in ESPN_PATH:
        return {}
    teams = _find_espn_game(sport, game["home_team"], game["away_team"], game["commence_time"])
    if not teams:
        return {}
    games = []  # (team id, [(espn event id, parsed box score)] newest first), both teams
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        for team_id in teams.values():
            event_ids = _recent_events(sport, team_id, game["commence_time"])
            boxes = list(pool.map(lambda eid: _safe_box(sport, eid), event_ids))
            games.append((team_id, [(eid, box) for eid, box in zip(event_ids, boxes) if box]))

    out = {}
    for name, markets in players.items():
        key = name_key(name)
        for team_id, team_games in games:
            # Only rows for THIS team: a player also shows up in the box scores
            # of the other team's games against them, which aren't their recent form.
            mine = [(eid, p) for eid, box in team_games
                    for pname, p in box["players"].items() if name_key(pname) == key and p["team"] == team_id]
            if not mine:
                continue
            out[name] = {
                "events": [eid for eid, _ in mine],
                "values": {m: [p["stats"].get(m) for _, p in mine] for m in markets},
            }
            out[name]["proj"] = {m: projection(v) for m, v in out[name]["values"].items()}
            break
    return out


def _safe_box(sport, event_id):
    try:
        return _box_score(sport, event_id)
    except Exception:
        return None  # one bad game shouldn't sink the rest
