"""PropLine API client -- event lookup, prop-odds fetch, and whole-slate scanning."""

import datetime
import json
import urllib.parse
import urllib.request

from scoring import MARKETS_BY_SPORT, BASKETBALL_MARKETS, extract_raw_all_books, build_report


def api_get(path, api_key, extra_params=None):
    params = {"apiKey": api_key}
    if extra_params:
        params.update(extra_params)
    url = f"https://api.prop-line.com/v1{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_props(sport_key, event_id, api_key, markets):
    return api_get(
        f"/sports/{sport_key}/events/{event_id}/odds",
        api_key,
        {"markets": ",".join(markets)},
    )


def list_upcoming_events(sport_key, api_key):
    """Simplified list of upcoming games for the game-browser feature --
    just enough to display and click, not full odds."""
    events = api_get(f"/sports/{sport_key}/events", api_key)
    simplified = []
    for e in events:
        simplified.append({
            "id": e.get("id"),
            "home_team": e.get("home_team", ""),
            "away_team": e.get("away_team", ""),
            "commence_time": e.get("commence_time", ""),
        })
    return simplified


def fetch_event_stats(sport_key, event_id, api_key):
    """Final (or in-progress) box score for one event -- {status, home_score,
    away_score, stats: [{player_name, team_abbr, stat_type, stat_value}, ...]}.
    status is "upcoming" with an empty stats list until the game starts, and
    "final" once it's over -- see result_grading.py for how this gets turned
    into W/L for a logged pick."""
    return api_get(f"/sports/{sport_key}/events/{event_id}/stats", api_key)


def utc_to_local_date_str(utc_iso_str):
    """Convert a PropLine UTC timestamp to the local machine's calendar date.
    Needed because comparing raw UTC date strings against a local date was
    silently excluding evening games -- e.g. an 8pm Eastern tip-off is already
    past midnight UTC, landing on the "next day" in UTC even though it's
    still tonight locally."""
    if not utc_iso_str:
        return ""
    try:
        dt_utc = datetime.datetime.fromisoformat(utc_iso_str.replace("Z", "+00:00"))
        return dt_utc.astimezone().date().isoformat()
    except ValueError:
        return utc_iso_str[:10]  # fallback if the timestamp is malformed


def scan_slate(sport_key, date_str, api_key, bar, include_raw=True):
    """Scan every game on a given date (YYYY-MM-DD, local calendar date) and
    merge results into one combined, re-sorted list. Each row is tagged with
    which matchup it came from. A game that fails to fetch is skipped, not
    fatal to the rest -- reported back via skipped_games so the caller can
    show what happened.

    include_raw=False skips building the raw all-books dump entirely -- for a
    full slate that's megabytes per game (a 12-game MLB slate measured at
    ~18MB), which blew past the browser's localStorage quota and made scanned
    tabs silently fail to save. It's only ever used for the optional "Show
    raw data" debug panel, so slate scans skip it; single-game scans keep it.

    Also returns any_prizepicks_board: whether PrizePicks had posted ANY
    props at all for any scanned game. PrizePicks tends to post its board
    much closer to game day than the sportsbooks in CONSENSUS_BOOKS, so a
    slate scanned too far ahead can find real games with zero PrizePicks
    legs to grade -- a very different situation from PrizePicks having legs
    that just don't overlap consensus coverage, and worth telling apart in
    the caller's error message."""
    all_events = list_upcoming_events(sport_key, api_key)
    matching = [e for e in all_events if utc_to_local_date_str(e.get("commence_time")) == date_str]

    markets = MARKETS_BY_SPORT.get(sport_key, BASKETBALL_MARKETS)
    combined_rows = []
    combined_raw = []
    scanned_games = []
    scanned_game_events = []
    skipped_games = []
    any_prizepicks_board = False

    for event in matching:
        matchup = f"{event['away_team']} @ {event['home_team']}"
        try:
            full_event = fetch_props(sport_key, event["id"], api_key, markets)
        except Exception as e:
            skipped_games.append(f"{matchup} ({type(e).__name__})")
            continue

        if include_raw:
            raw = extract_raw_all_books(full_event)
            for m in raw:
                m_copy = dict(m)
                m_copy["_matchup"] = matchup
                combined_raw.append(m_copy)

        if any(b.get("key") == "prizepicks" for b in full_event.get("bookmakers", [])):
            any_prizepicks_board = True

        rows, _ = build_report(full_event, bar)
        for r in rows:
            r["matchup"] = matchup
            # Tag the exact event + sport a row came from at scan time, not
            # reconstructed later from the matchup string -- lets a logged
            # pick be re-checked against real results with a direct API call
            # instead of a fragile team-name/date re-lookup. See result_grading.py.
            r["eventId"] = event["id"]
            r["sport"] = sport_key
        combined_rows.extend(rows)
        scanned_games.append(matchup)
        scanned_game_events.append({"matchup": matchup, "eventId": event["id"]})

    combined_rows.sort(key=lambda r: r["margin"] if r["margin"] is not None else float("-inf"), reverse=True)
    return combined_rows, combined_raw, scanned_games, skipped_games, scanned_game_events, any_prizepicks_board
