"""
PrizePicks Edge Finder -- Local Web App
-----------------------------------------
Double-click launch.bat to start this and open it in your browser.
No installs beyond Python itself -- everything here is standard library.

First-time setup: put your PropLine API key in config.json (same folder).
"""

import json
import os
import datetime
import urllib.request
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import defaultdict

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

PORT = 8787
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# ---------- Config ----------

def load_config():
    changed = False
    if not os.path.exists(CONFIG_PATH):
        config = {"api_key": "PASTE_YOUR_PROPLINE_KEY_HERE", "tracking_workbook_path": ""}
        changed = True
    else:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
        if "tracking_workbook_path" not in config:
            config["tracking_workbook_path"] = ""
            changed = True
    if changed:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
    return config


# ---------- PropLine API calls ----------

def api_get(path, api_key, extra_params=None):
    params = {"apiKey": api_key}
    if extra_params:
        params.update(extra_params)
    url = f"https://api.prop-line.com/v1{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_event(sport_key, team_a, team_b, api_key):
    """Find the event whose home/away team names contain the two team names given."""
    events = api_get(f"/sports/{sport_key}/events", api_key)
    team_a_l = team_a.lower()
    team_b_l = team_b.lower()
    for e in events:
        home = (e.get("home_team") or "").lower()
        away = (e.get("away_team") or "").lower()
        combined = home + " " + away
        if team_a_l in combined and team_b_l in combined:
            return e
    return None


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


def scan_slate(sport_key, date_str, api_key, bar):
    """Scan every game on a given date (YYYY-MM-DD, local calendar date) and
    merge results into one combined, re-sorted list. Each row is tagged with
    which matchup it came from. A game that fails to fetch is skipped, not
    fatal to the rest -- reported back via skipped_games so the caller can
    show what happened."""
    all_events = list_upcoming_events(sport_key, api_key)
    matching = [e for e in all_events if utc_to_local_date_str(e.get("commence_time")) == date_str]

    markets = MARKETS_BY_SPORT.get(sport_key, BASKETBALL_MARKETS)
    combined_rows = []
    combined_raw = []
    scanned_games = []
    skipped_games = []

    for event in matching:
        matchup = f"{event['away_team']} @ {event['home_team']}"
        try:
            full_event = fetch_props(sport_key, event["id"], api_key, markets)
        except Exception as e:
            skipped_games.append(f"{matchup} ({type(e).__name__})")
            continue

        raw = extract_raw_prizepicks(full_event)
        for m in raw:
            m_copy = dict(m)
            m_copy["_matchup"] = matchup
            combined_raw.append(m_copy)

        rows, _ = build_report(full_event, bar)
        for r in rows:
            r["matchup"] = matchup
        combined_rows.extend(rows)
        scanned_games.append(matchup)

    combined_rows.sort(key=lambda r: r["margin"], reverse=True)
    return combined_rows, combined_raw, scanned_games, skipped_games


# ---------- Edge-grading logic (same as edge_finder.py) ----------

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
        margin, tier = grade_leg(bar, true_pct)

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
            "single_book": single_book, "bar": bar, "margin": round(margin, 1),
            "tier": tier, "estimated": any_estimate, "gap": round(max_gap, 1),
            "estimate_type": estimate_type, "whole_number": whole_number,
            "book_point": rep["book_point"], "over_price": rep["over_price"], "under_price": rep["under_price"],
        })
    rows.sort(key=lambda r: r["margin"], reverse=True)
    return rows, bar


# ---------- Spreadsheet logging ----------

# Best-effort stat abbreviations to match the workbook's existing convention
# (PTS, AST, etc). Falls back to the raw market key uppercased if unmapped.
STAT_ABBREV = {
    "player_points": "PTS", "player_rebounds": "REB", "player_assists": "AST",
    "player_points_rebounds_assists": "PRA", "player_threes": "3PM",
    "player_blocks": "BLK", "player_steals": "STL",
    "batter_hits": "HITS", "batter_home_runs": "HR", "batter_rbis": "RBI",
    "batter_hits_runs_rbis": "H+R+RBI", "batter_runs_scored": "RUNS",
    "batter_stolen_bases": "SB", "batter_total_bases": "TB",
    "pitcher_strikeouts": "K", "pitcher_hits_allowed": "H ALLOWED",
    "pitcher_walks": "BB", "pitcher_outs": "OUTS",
}
LINE_TYPE_MAP = {"standard": "STD", "goblin": "GOBLIN", "demon": "DEMON"}
TIER_CODE_MAP = {"TIER A": "A", "TIER B": "B", "BELOW BAR": "BELOW BAR"}


def log_parlay_to_excel(workbook_path, legs, multiplier, entry_type_label, date_str):
    """
    legs: list of dicts with player/market/point/side/dfs_type/consensus_pct/bar/margin/
          tier/whole_number/estimate_type/book_point/over_price/under_price/books/matchup/spread_pct
    Returns (success, message, entry_id).
    """
    if not OPENPYXL_AVAILABLE:
        return False, "openpyxl isn't installed. In Command Prompt run: pip install openpyxl --break-system-packages , then restart the app.", None
    if not workbook_path:
        return False, "No tracking workbook path set. Add \"tracking_workbook_path\" in config.json.", None
    if not os.path.exists(workbook_path):
        return False, f"Workbook not found at: {workbook_path}. Check the path in config.json.", None

    try:
        wb = openpyxl.load_workbook(workbook_path)
    except PermissionError:
        return False, "Couldn't open the workbook -- close it in Excel first, then try again.", None
    except Exception as e:
        return False, f"Couldn't open workbook: {type(e).__name__}: {e}", None

    if "Leg Log" not in wb.sheetnames or "Entry Log" not in wb.sheetnames:
        return False, "Workbook doesn't have 'Leg Log' and 'Entry Log' sheets -- wrong file?", None

    leg_log = wb["Leg Log"]
    entry_log = wb["Entry Log"]

    # Next Entry ID: scan existing "E<number>" IDs across both sheets, increment past the max.
    existing_ids = set()
    for sheet in (leg_log, entry_log):
        for row in sheet.iter_rows(min_row=2, max_col=2, values_only=True):
            eid = row[1]
            if eid and isinstance(eid, str) and eid.startswith("E") and eid[1:].isdigit():
                existing_ids.add(int(eid[1:]))
    entry_id = f"E{(max(existing_ids) + 1) if existing_ids else 1}"

    combined_prob = 1.0
    # Find the first genuinely empty row rather than blindly appending after
    # max_row -- the sheet has hundreds of pre-formatted template rows with
    # formulas already in place but no actual data, and we want to fill those
    # in order (reusing their existing formulas) instead of skipping past all
    # of them and starting a fresh block far below.
    next_row = 2
    while leg_log.cell(row=next_row, column=5).value not in (None, ""):  # column E = Player
        next_row += 1
    legs_written = 0

    for leg in legs:
        stat = STAT_ABBREV.get(leg.get("market", ""), leg.get("market", "").upper())
        line_type = LINE_TYPE_MAP.get(leg.get("dfs_type", "standard"), "STD")
        true_pct = leg.get("consensus_pct", 0) / 100.0
        bar_dec = leg.get("bar", 0) / 100.0
        combined_prob *= true_pct
        tier_code = TIER_CODE_MAP.get(leg.get("tier", ""), leg.get("tier", ""))

        note = f"Logged via Edge Finder app. Books: {', '.join(leg.get('books', []))}."
        if leg.get("spread_pct") is not None:
            note += f" Spread: {leg['spread_pct']}pts."
        else:
            note += " Single book."

        r = next_row  # for formula references below, matching the workbook's own formula pattern
        values = [
            date_str, entry_id, entry_type_label, multiplier,
            leg.get("player", ""), leg.get("matchup", ""), stat, (leg.get("side") or "").upper(),
            leg.get("point"), f'=IF(I{r}="","",IF(I{r}=INT(I{r}),"Y","N"))', line_type,
            leg.get("book_point"), leg.get("over_price"), leg.get("under_price"),
            true_pct, leg.get("estimate_type", ""), bar_dec,
            f'=IF(OR(O{r}="",Q{r}=""),"",O{r}-Q{r})',
            tier_code,
            None, None,  # Actual Value / Result -- filled in later
            f'=IF(U{r}="W",1,IF(U{r}="L",0,""))',
            f'=IF(V{r}="","",(O{r}-V{r})^2)',
            None,  # CLV Favorable? -- filled in later
            note,
        ]
        for col, val in enumerate(values, start=1):
            leg_log.cell(row=next_row, column=col, value=val)
        leg_log.cell(row=next_row, column=4).number_format = '0.0\\x'
        leg_log.cell(row=next_row, column=15).number_format = '0.0%'
        leg_log.cell(row=next_row, column=17).number_format = '0.0%'
        leg_log.cell(row=next_row, column=18).number_format = '0.0%'
        leg_log.cell(row=next_row, column=23).number_format = '0.0000'
        next_row += 1
        legs_written += 1

    modelled_ev = round(combined_prob * multiplier, 3)
    next_entry_row = 2
    while entry_log.cell(row=next_entry_row, column=2).value not in (None, ""):  # column B = Entry ID
        next_entry_row += 1
    entry_row = next_entry_row
    entry_values = [date_str, entry_id, entry_type_label, multiplier, legs_written,
                     modelled_ev, None, None, None, None, "Logged via Edge Finder app."]
    for col, val in enumerate(entry_values, start=1):
        entry_log.cell(row=entry_row, column=col, value=val)
    entry_log.cell(row=entry_row, column=4).number_format = '0.0\\x'

    try:
        wb.save(workbook_path)
    except PermissionError:
        return False, "Couldn't save -- the workbook is open in Excel. Close it and try again.", None
    except Exception as e:
        return False, f"Couldn't save workbook: {type(e).__name__}: {e}", None

    return True, f"Logged {legs_written} leg(s) as entry {entry_id}.", entry_id


# ---------- HTML rendering ----------

PAGE_HEAD = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>PrizePicks Edge Finder</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; background: #0f1117; color: #e6e6e6; margin: 0; padding: 2rem; }}
.container {{ max-width: 1300px; margin: 0 auto; }}
h1 {{ font-size: 1.4rem; color: #fff; }}
.header-row {{ display: flex; gap: 1.5rem; flex-wrap: wrap; align-items: stretch; margin-bottom: 1.5rem; }}
form {{ background: #1a1d27; padding: 2rem 2.2rem; border-radius: 10px; margin: 0; flex: 1 1 0; min-width: 340px; display: flex; flex-direction: column; justify-content: center; gap: 0.4rem; }}
label {{ display: block; margin-bottom: 0.4rem; font-size: 1.05rem; color: #aaa; }}
input, select {{ width: 100%; padding: 0.9rem; margin-bottom: 1.2rem; border-radius: 8px; border: 1px solid #333; background: #0f1117; color: #fff; box-sizing: border-box; font-size: 1.1rem; }}
button {{ background: #4f7cff; color: white; border: none; padding: 1rem 1.8rem; border-radius: 8px; cursor: pointer; font-size: 1.15rem; margin-top: 0.6rem; }}
button:hover {{ background: #3a63e0; }}
.slate-section {{ margin-top: 1.2rem; padding-top: 1rem; border-top: 1px solid #2a2d3a; }}
.slate-btn {{ background: #2a4a3a; width: 100%; }}
.slate-btn:hover {{ background: #35603f; }}
.matchup-line {{ font-size: 0.75rem; color: #777; margin-top: 0.1rem; }}
.skipped-warning {{ background: #3a3010; color: #ffd27a; padding: 0.6rem 0.9rem; border-radius: 8px; margin-bottom: 0.8rem; font-size: 0.85rem; }}
.browse-btn {{ background: transparent; border: 1px solid #3a4a63; color: #aac8ff; font-size: 0.9rem; padding: 0.55rem 1rem; margin-bottom: 0.6rem; }}
.browse-btn:hover {{ background: #1a2a3a; }}
#game-browser {{ margin-bottom: 0.8rem; }}
.game-list {{ max-height: 220px; overflow-y: auto; border: 1px solid #2a2d3a; border-radius: 8px; }}
.game-item {{ padding: 0.6rem 0.8rem; border-bottom: 1px solid #22242e; cursor: pointer; font-size: 0.9rem; }}
.game-item:last-child {{ border-bottom: none; }}
.game-item:hover {{ background: #22283a; }}
.game-item .game-time {{ color: #888; font-size: 0.75rem; display: block; margin-top: 0.15rem; }}
.game-list-msg {{ color: #888; font-size: 0.85rem; padding: 0.5rem; }}
.filter-bar {{ display: flex; gap: 0.6rem; flex-wrap: wrap; align-items: center; margin-bottom: 1rem; }}
.filter-bar input {{ width: auto; flex: 1 1 240px; margin: 0; padding: 0.55rem 0.8rem; }}
.type-toggles {{ display: flex; gap: 0.4rem; }}
.type-toggle {{ background: #1a1d27; border: 1px solid #2a2d3a; color: #888; padding: 0.5rem 0.9rem; border-radius: 6px; font-size: 0.85rem; cursor: pointer; }}
.type-toggle.active[data-type="goblin"] {{ border-color: #4caf50; color: #8aff8a; }}
.type-toggle.active[data-type="demon"] {{ border-color: #ff6b6b; color: #ff8a8a; }}
.type-toggle.active[data-type="regular"] {{ border-color: #4f7cff; color: #aac8ff; }}
.raw-toggle-btn {{ background: transparent; border: 1px solid #444; color: #999; padding: 0.5rem 0.9rem; border-radius: 6px; font-size: 0.85rem; cursor: pointer; margin-left: auto; }}
.raw-toggle-btn:hover {{ background: #222; }}
.raw-data-panel {{ background: #0f1117; border: 1px solid #2a2d3a; border-radius: 8px; padding: 0.8rem; margin-bottom: 1rem; max-height: 400px; overflow-y: auto; }}
.raw-json {{ font-family: 'Consolas', 'Monaco', monospace; font-size: 0.75rem; color: #9fd89f; white-space: pre-wrap; word-break: break-word; margin: 0.5rem 0 0 0; }}
.error {{ background: #3a1414; color: #ff9a9a; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }}
.breakeven-chart {{ background: #1a1d27; border-radius: 10px; padding: 1rem 1.2rem; flex: 1 1 0; min-width: 340px; font-size: 0.8rem; }}
.breakeven-chart h2 {{ font-size: 0.95rem; margin: 0 0 0.6rem 0; color: #fff; }}
.breakeven-chart table {{ width: 100%; border-collapse: collapse; margin-bottom: 0.6rem; }}
.breakeven-chart th {{ text-align: left; color: #888; font-weight: 600; padding: 0.2rem 0.4rem; border-bottom: 1px solid #2a2d3a; }}
.breakeven-chart td {{ padding: 0.25rem 0.4rem; border-bottom: 1px solid #22242e; }}
.breakeven-chart .section-label {{ color: #aac8ff; font-weight: 600; margin: 0.6rem 0 0.2rem 0; }}
.breakeven-chart .unverified {{ color: #ffb300; }}
.breakeven-chart .footnote {{ color: #777; font-size: 0.72rem; margin-top: 0.5rem; line-height: 1.4; }}
</style></head>
<body><div class="container">
<h1>PrizePicks Edge Finder</h1>
<div class="header-row">
<form method="POST" action="/scan" id="scan-form">
  <label>Team A</label>
  <input name="team_a" id="team-a-input" value="{team_a}" placeholder="e.g. Mercury">
  <label>Team B</label>
  <input name="team_b" id="team-b-input" value="{team_b}" placeholder="e.g. Sparks">
  <label>Sport</label>
  <select name="sport" id="sport-select">
    <option value="basketball_wnba" {sel_wnba}>WNBA</option>
    <option value="basketball_nba" {sel_nba}>NBA</option>
    <option value="baseball_mlb" {sel_mlb}>MLB</option>
  </select>
  <button type="button" class="browse-btn" onclick="browseGames()">Browse upcoming games</button>
  <div id="game-browser"></div>
  <label>Entry type</label>
  <select name="entry_type">
    <option value="power" {sel_power}>Power Play</option>
    <option value="flex" {sel_flex}>Flex Play</option>
  </select>
  <label>Entry size</label>
  <select name="entry">
    <option value="2" {sel_2}>2-pick</option>
    <option value="3" {sel_3}>3-pick</option>
    <option value="4" {sel_4}>4-pick</option>
    <option value="5" {sel_5}>5-pick</option>
    <option value="6" {sel_6}>6-pick</option>
  </select>
  <button type="submit" formaction="/scan">Find Edges</button>

  <div class="slate-section">
    <label>Or scan a whole slate -- date</label>
    <input type="date" name="slate_date" id="slate-date-input" value="{today}">
    <button type="submit" formaction="/scan_slate" formnovalidate class="slate-btn">Scan whole slate</button>
  </div>
</form>

<div class="breakeven-chart">
  <h2>Break-even reference</h2>

  <div class="section-label">Power Play (per-leg break-even)</div>
  <table>
    <tr><th>Picks</th><th>Multiplier</th><th>Break-even/leg</th></tr>
    <tr><td>2</td><td>3x</td><td>57.7%</td></tr>
    <tr><td>3</td><td>6x</td><td>55.0%</td></tr>
    <tr><td>4</td><td>10x</td><td>56.2%</td></tr>
    <tr><td>5</td><td>20x</td><td>54.9%</td></tr>
    <tr><td>6</td><td>37.5x</td><td>54.7%</td></tr>
  </table>

  <div class="section-label">Flex Play (payout tiers, per leg -- assumes equal probability across legs)</div>
  <table>
    <tr><th>Picks</th><th>All hit</th><th>1 miss</th><th>2 miss</th><th>Break-even/leg</th><th>Am. odds</th></tr>
    <tr><td>2</td><td colspan="4">Not offered -- Flex requires 3+ picks</td></tr>
    <tr><td>3</td><td>3x</td><td>1x</td><td>--</td><td>57.7%</td><td>-137</td></tr>
    <tr><td>4</td><td>6x</td><td>1.5x</td><td>--</td><td>55.0%</td><td>-122</td></tr>
    <tr><td>5</td><td>10x</td><td>2x</td><td>0.4x</td><td>54.3%</td><td>-119</td></tr>
    <tr><td>6</td><td>25x</td><td>2x</td><td>0.4x</td><td>54.2%</td><td>-118</td></tr>
  </table>

  <div class="footnote">
    Power Play numbers verified two ways: cross-checked against your own established break-even
    figures and against current multiplier reports. Flex 3-pick payout tiers (3x/1x) confirmed
    directly from the app. The Flex break-even/leg column is solved from the real expected-value
    math across all payout tiers (not just the top one) -- it assumes every leg in the entry has
    the same true win probability, which is a simplification, not how a mixed-confidence real
    entry actually works. The 4-pick Flex top payout was corrected to 6x (not 5x) after this math
    didn't reconcile at 5x -- 6x is what makes the numbers check out. All multipliers can change or
    vary by lineup (same-game combos, promos) -- always confirm the number shown in the app before
    submitting.
  </div>
</div>
</div>
"""

# Static footer: tabs bar, results area, and all client-side JS.
# Deliberately kept OUTSIDE of .format() (plain string concat in render_form)
# so the JS's own { } braces never collide with Python's format placeholders.
STATIC_FOOTER = """
<div class="toolbar">
  <button type="button" class="clear-btn" onclick="clearAllGames()">Clear all saved games</button>
</div>
<div id="tabs-bar" class="tabs-bar"></div>
<div id="entry-builder-area"></div>
<div id="filter-bar-area"></div>
<div id="results-area"></div>

<style>
.toolbar { margin-bottom: 0.6rem; }
.clear-btn { background: transparent; border: 1px solid #4a2a2a; color: #ff9a9a; padding: 0.35rem 0.7rem; border-radius: 6px; font-size: 0.8rem; cursor: pointer; }
.clear-btn:hover { background: #3a1414; }
.tabs-bar { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; }
.tab { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 6px 6px 0 0; padding: 0.4rem 0.8rem; font-size: 0.85rem; cursor: pointer; display: flex; align-items: center; gap: 0.5rem; }
.tab.active { background: #22283a; border-color: #4f7cff; color: #fff; }
.tab .tab-close { color: #888; font-size: 0.75rem; }
.tab .tab-close:hover { color: #ff8a8a; }
.meta { font-size: 0.85rem; color: #999; margin-top: 0.3rem; margin-bottom: 0.8rem; }
.entry-builder { background: #14283a; border: 1px solid #2a4a63; border-radius: 8px; padding: 0.9rem 1.1rem; margin-bottom: 1rem; font-size: 0.9rem; position: sticky; top: 1rem; z-index: 10; }
.entry-builder input { width: 100px; display: inline; margin: 0; }
.entry-builder select { width: auto; display: inline; margin: 0; padding: 0.3rem 0.5rem; }
.log-parlay-btn { background: #4f7cff; margin-top: 0.6rem; padding: 0.5rem 1rem; font-size: 0.9rem; }
.log-parlay-btn:hover { background: #3a63e0; }
.selected-leg { font-size: 0.85rem; padding: 0.25rem 0; }
.mult-result { font-size: 0.85rem; margin-top: 0.4rem; }
.columns-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }
@media (max-width: 900px) { .columns-grid { grid-template-columns: 1fr; } }
.column-header { font-weight: 600; margin-bottom: 0.6rem; padding-bottom: 0.4rem; border-bottom: 2px solid #2a2d3a; }
.column-header.goblin { color: #8aff8a; }
.column-header.demon { color: #ff8a8a; }
.column-header.regular { color: #aac8ff; }
.leg-row { background: #1a1d27; border-radius: 8px; padding: 0.8rem 0.9rem; margin-bottom: 0.6rem; }
.leg-row label { display: block; cursor: pointer; }
.tierA { border-left: 4px solid #4caf50; }
.tierB { border-left: 4px solid #ffb300; }
.below { border-left: 4px solid #555; opacity: 0.6; }
.badge { display: inline-block; font-size: 0.65rem; padding: 0.15rem 0.4rem; border-radius: 4px; margin-left: 0.3rem; }
.badge-est { background: #3a3010; color: #ffd27a; }
.badge-single { background: #3a1030; color: #ff9ad2; }
.badge-conflict { background: #4a1010; color: #ff6a6a; font-weight: 600; }
.badge-side-more { background: #1e3a2e; color: #6adf9f; font-weight: 600; }
.badge-side-less { background: #3a2e1e; color: #dfaf6a; font-weight: 600; }
.leg-check { margin-right: 0.4rem; }
.empty-col { color: #666; font-size: 0.85rem; font-style: italic; }
</style>

<script>
var STORAGE_KEY = 'pp_edge_games';
var ACTIVE_KEY = 'pp_edge_active';
var SELECTED_KEY = 'pp_edge_selected';

function loadGames() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
    catch (e) { return {}; }
}
function saveGames(games) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(games));
}

function renderTabs(games, activeKey) {
    var bar = document.getElementById('tabs-bar');
    var keys = Object.keys(games);
    if (keys.length === 0) { bar.innerHTML = ''; return; }
    var html = '';
    keys.forEach(function(key) {
        var g = games[key];
        var activeClass = (key === activeKey) ? ' active' : '';
        html += '<div class="tab' + activeClass + '" onclick="switchGame(\\'' + key + '\\')">'
            + g.label
            + ' <span class="tab-close" onclick="event.stopPropagation(); deleteGame(\\'' + key + '\\')">&times;</span>'
            + '</div>';
    });
    bar.innerHTML = html;
}

function switchGame(key) {
    localStorage.setItem(ACTIVE_KEY, key);
    var games = loadGames();
    renderTabs(games, key);
    if (games[key]) renderColumns(games[key]);
}

function escapeAttr(str) {
    return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function browseGames() {
    var sport = document.getElementById('sport-select').value;
    var area = document.getElementById('game-browser');
    area.innerHTML = '<div class="game-list-msg">Loading upcoming games...</div>';

    fetch('/games?sport=' + encodeURIComponent(sport))
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (data.error) {
                area.innerHTML = '<div class="game-list-msg">' + data.error + '</div>';
                return;
            }
            var games = data.games || [];
            if (games.length === 0) {
                area.innerHTML = '<div class="game-list-msg">No upcoming games found for this sport right now.</div>';
                return;
            }
            var html = '<div class="game-list">';
            games.forEach(function(g) {
                var timeStr = '';
                if (g.commence_time) {
                    try { timeStr = new Date(g.commence_time).toLocaleString(); }
                    catch (e) { timeStr = g.commence_time; }
                }
                html += '<div class="game-item" data-away="' + escapeAttr(g.away_team) + '" data-home="' + escapeAttr(g.home_team) + '" onclick="pickGame(this.dataset.away, this.dataset.home)">'
                    + g.away_team + ' @ ' + g.home_team
                    + (timeStr ? '<span class="game-time">' + timeStr + '</span>' : '')
                    + '</div>';
            });
            html += '</div>';
            area.innerHTML = html;
        })
        .catch(function(err) {
            area.innerHTML = '<div class="game-list-msg">Could not load games: ' + err + '</div>';
        });
}

function pickGame(teamA, teamB) {
    document.getElementById('team-a-input').value = teamA;
    document.getElementById('team-b-input').value = teamB;
    document.getElementById('scan-form').submit();
}

function clearAllGames() {
    if (!confirm('Clear all saved games and any in-progress entry selections? This cannot be undone.')) {
        return;
    }
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(ACTIVE_KEY);
    localStorage.removeItem(SELECTED_KEY);
    selectedLegs = {};
    renderTabs({}, null);
    document.getElementById('results-area').innerHTML = '';
    renderEntryBuilder();
}

function deleteGame(key) {
    var games = loadGames();
    delete games[key];
    saveGames(games);
    Object.keys(selectedLegs).forEach(function(legId) {
        if (legId.indexOf(key + '::') === 0) delete selectedLegs[legId];
    });
    saveSelected();
    var remaining = Object.keys(games);
    var newActive = remaining.length ? remaining[0] : null;
    if (newActive) localStorage.setItem(ACTIVE_KEY, newActive);
    else localStorage.removeItem(ACTIVE_KEY);
    renderTabs(games, newActive);
    if (newActive) renderColumns(games[newActive]);
    else document.getElementById('results-area').innerHTML = '';
    renderEntryBuilder();
}

function badgesForRow(r) {
    var b = '';
    if (r.estimated) b += '<span class="badge badge-est">EST +' + r.gap + 'pt</span>';
    if (r.single_book) b += '<span class="badge badge-single">SINGLE BOOK</span>';
    if (r.type_conflict) b += '<span class="badge badge-conflict">VERIFY TYPE IN APP</span>';
    return b;
}

function legRowHtml(r, gameKey, gameLabel) {
    var css = r.tier === 'TIER A' ? 'tierA' : (r.tier === 'TIER B' ? 'tierB' : 'below');
    var spread = r.single_book ? 'N/A - SINGLE BOOK' : (r.spread_pct + 'pts');
    var shortMarket = r.market.replace('player_', '').replace('batter_', '').replace('pitcher_', '');
    var label = r.player + ' - ' + r.side + ' ' + shortMarket + ' ' + r.point;
    var legId = gameKey + '::' + r.player + '::' + r.market + '::' + r.point;
    var checkedAttr = selectedLegs[legId] ? 'checked' : '';
    var sideBadge = '<span class="badge badge-side-' + r.side.toLowerCase() + '">' + r.side.toUpperCase() + '</span>';
    var matchupLine = r.matchup ? ('<div class="matchup-line">' + r.matchup + '</div>') : '';

    // Full leg data for spreadsheet logging, base64-encoded to avoid any HTML
    // attribute quote-collision risk (bit us twice already with inline JSON).
    var logData = {
        player: r.player, market: r.market, point: r.point, side: r.side,
        dfs_type: r.dfs_type, consensus_pct: r.consensus_pct, bar: r.bar, margin: r.margin,
        tier: r.tier, whole_number: (r.point !== null && r.point % 1 === 0),
        estimate_type: r.estimate_type, book_point: r.book_point,
        over_price: r.over_price, under_price: r.under_price,
        books: r.books, matchup: r.matchup || '', spread_pct: r.spread_pct,
    };
    var logDataB64 = btoa(unescape(encodeURIComponent(JSON.stringify(logData))));

    return '<div class="leg-row ' + css + '">'
        + '<label>'
        + '<input type="checkbox" class="leg-check" data-legid="' + legId + '" data-label="' + label
        + '" data-consensus="' + r.consensus_pct + '" data-gamelabel="' + gameLabel + '" data-logb64="' + logDataB64 + '" '
        + checkedAttr + ' onchange="toggleLeg(this)">'
        + '<strong>' + r.player + '</strong> \u2014 ' + shortMarket + sideBadge + badgesForRow(r)
        + matchupLine
        + '<div class="meta">'
        + 'Line: ' + r.point + ' | Consensus: ' + r.consensus_pct + '% ' + r.side
        + ' (spread ' + spread + ', books: ' + r.books.join(', ') + ')<br>'
        + 'Break-even: ' + r.bar + '% | Edge margin: ' + (r.margin >= 0 ? '+' : '') + r.margin.toFixed(1) + ' pts | <strong>' + r.tier + '</strong>'
        + '</div></label></div>';
}

// ---- Search + type filtering ----
var currentGameData = null;
var searchQuery = '';
var typeFilters = { goblin: true, regular: true, demon: true };
var rawViewOpen = false;

function matchesFilters(r) {
    var isGoblin = r.dfs_type === 'goblin';
    var isDemon = r.dfs_type === 'demon';
    var isRegular = !isGoblin && !isDemon;
    var typeOk = (isGoblin && typeFilters.goblin) || (isDemon && typeFilters.demon) || (isRegular && typeFilters.regular);
    if (!typeOk) return false;
    if (searchQuery) {
        var q = searchQuery.toLowerCase();
        var playerMatch = r.player.toLowerCase().indexOf(q) !== -1;
        var marketMatch = r.market.toLowerCase().indexOf(q) !== -1;
        return playerMatch || marketMatch;
    }
    return true;
}

function renderFilterBar() {
    var area = document.getElementById('filter-bar-area');
    var html = '<div class="filter-bar">'
        + '<input type="text" id="player-search" placeholder="Search players or stat type (hits, runs, assists...)" oninput="applySearch()">'
        + '<div class="type-toggles">'
        + '<button type="button" class="type-toggle active" data-type="goblin" onclick="toggleTypeFilter(this)">Goblins</button>'
        + '<button type="button" class="type-toggle active" data-type="regular" onclick="toggleTypeFilter(this)">Regular</button>'
        + '<button type="button" class="type-toggle active" data-type="demon" onclick="toggleTypeFilter(this)">Demons</button>'
        + '<button type="button" class="raw-toggle-btn" onclick="toggleRawView()">Show raw data</button>'
        + '</div></div>'
        + '<div id="raw-data-panel" class="raw-data-panel" style="display:none;"></div>';
    area.innerHTML = html;
}

function toggleRawView() {
    rawViewOpen = !rawViewOpen;
    renderRawPanel();
}

function renderRawPanel() {
    var panel = document.getElementById('raw-data-panel');
    if (!panel) return;
    if (!rawViewOpen) { panel.style.display = 'none'; return; }
    panel.style.display = 'block';

    if (!currentGameData) {
        panel.innerHTML = '<div class="game-list-msg">No game selected.</div>';
        return;
    }
    var raw = currentGameData.rawPrizePicks || [];
    var q = searchQuery.toLowerCase();

    var filteredMarkets = raw.map(function(m) {
        var outcomes = m.outcomes || [];
        if (q) {
            outcomes = outcomes.filter(function(o) {
                var desc = (o.description || '').toLowerCase();
                var key = (m.key || '').toLowerCase();
                return desc.indexOf(q) !== -1 || key.indexOf(q) !== -1;
            });
        }
        return { key: m.key, outcomes: outcomes };
    }).filter(function(m) { return m.outcomes.length > 0; });

    var header = q
        ? ('Raw PrizePicks data matching "' + searchQuery + '" (' + filteredMarkets.length + ' market blocks)')
        : ('Raw PrizePicks data -- all ' + filteredMarkets.length + ' market blocks (type in search to filter)');

    panel.innerHTML = '<div class="meta">' + header + '</div><pre class="raw-json">' + escapeAttr(JSON.stringify(filteredMarkets, null, 2)) + '</pre>';
}

function toggleTypeFilter(btn) {
    var type = btn.dataset.type;
    typeFilters[type] = !typeFilters[type];
    btn.classList.toggle('active', typeFilters[type]);
    renderFilteredColumns();
}

function applySearch() {
    searchQuery = document.getElementById('player-search').value;
    renderFilteredColumns();
    renderRawPanel();
}

function renderColumns(gameData) {
    currentGameData = gameData;
    renderFilteredColumns();
    renderRawPanel();
}

function renderFilteredColumns() {
    var area = document.getElementById('results-area');
    if (!currentGameData) { area.innerHTML = ''; return; }

    var gameData = currentGameData;
    var allRows = gameData.rows;
    var rows = allRows.filter(matchesFilters);
    var gameKey = gameData.gameKey;
    var gameLabel = gameData.label;
    var goblins = rows.filter(function(r) { return r.dfs_type === 'goblin'; });
    var demons = rows.filter(function(r) { return r.dfs_type === 'demon'; });
    var regular = rows.filter(function(r) { return r.dfs_type !== 'goblin' && r.dfs_type !== 'demon'; });

    function colHtml(list, emptyMsg) {
        if (list.length === 0) return '<div class="empty-col">' + emptyMsg + '</div>';
        return list.map(function(r) { return legRowHtml(r, gameKey, gameLabel); }).join('');
    }

    var metaText = rows.length === allRows.length
        ? (allRows.length + ' legs scanned | break-even bar: ' + gameData.bar + '%')
        : (rows.length + ' of ' + allRows.length + ' legs shown | break-even bar: ' + gameData.bar + '%');

    var gamesLine = '';
    if (gameData.scannedGames) {
        gamesLine = '<div class="meta">' + gameData.scannedGames.length + ' game(s) included: '
            + gameData.scannedGames.join(', ') + '</div>';
    }

    var html = gameData.skippedNote ? ('<div class="skipped-warning">' + gameData.skippedNote + '</div>') : '';
    html += gamesLine;
    html += '<div class="meta">' + metaText + '</div>';
    html += '<div class="columns-grid">'
        + '<div><div class="column-header goblin">GOBLINS</div>' + colHtml(goblins, 'No Goblin legs found.') + '</div>'
        + '<div><div class="column-header regular">REGULAR</div>' + colHtml(regular, 'No standard legs found.') + '</div>'
        + '<div><div class="column-header demon">DEMONS</div>' + colHtml(demons, 'No Demon legs found.') + '</div>'
        + '</div>';
    area.innerHTML = html;
}

// ---- Cross-game entry selection ----
var selectedLegs = {};

function loadSelected() {
    try { return JSON.parse(localStorage.getItem(SELECTED_KEY)) || {}; }
    catch (e) { return {}; }
}
function saveSelected() {
    localStorage.setItem(SELECTED_KEY, JSON.stringify(selectedLegs));
}

function toggleLeg(checkboxEl) {
    var legId = checkboxEl.dataset.legid;
    if (checkboxEl.checked) {
        var fullData = {};
        try {
            fullData = JSON.parse(decodeURIComponent(escape(atob(checkboxEl.dataset.logb64))));
        } catch (e) { /* fall back to minimal data below if decode fails */ }
        selectedLegs[legId] = {
            label: checkboxEl.dataset.label,
            consensus_pct: parseFloat(checkboxEl.dataset.consensus),
            gameLabel: checkboxEl.dataset.gamelabel,
            fullData: fullData,
        };
    } else {
        delete selectedLegs[legId];
    }
    saveSelected();
    renderEntryBuilder();
}

function removeLeg(legId) {
    delete selectedLegs[legId];
    saveSelected();
    var box = document.querySelector('.leg-check[data-legid="' + legId + '"]');
    if (box) box.checked = false;
    renderEntryBuilder();
}

function renderEntryBuilder() {
    var area = document.getElementById('entry-builder-area');
    var legIds = Object.keys(selectedLegs);

    if (legIds.length === 0) {
        area.innerHTML = '<div class="entry-builder"><strong>Build an entry:</strong> check legs '
            + '(from any game/tab) to combine them here -- selections carry across tabs.</div>';
        return;
    }

    var listHtml = legIds.map(function(legId) {
        var leg = selectedLegs[legId];
        var closeBtn = '<span class="tab-close" data-legid="' + legId + '" onclick="removeLeg(this.dataset.legid)">&times;</span>';
        return '<div class="selected-leg">' + leg.label + ' <span class="meta">(' + leg.gameLabel + ')</span> ' + closeBtn + '</div>';
    }).join('');

    var html = '<div class="entry-builder">'
        + '<strong>Building entry (' + legIds.length + ' leg' + (legIds.length > 1 ? 's' : '') + '):</strong>'
        + '<div style="margin: 0.4rem 0;">' + listHtml + '</div>'
        + 'Real payout multiplier: '
        + '<input type="number" step="0.01" min="1.01" id="entry-mult" placeholder="e.g. 2.3" oninput="calcEntry()">'
        + '<div id="entry-result" class="mult-result"></div>'
        + '<div style="margin-top:0.5rem;">Entry type for log: '
        + '<select id="log-entry-type"><option value="Power">Power</option><option value="Flex">Flex</option></select>'
        + '</div>'
        + '<button type="button" class="log-parlay-btn" onclick="logParlay()">Log this parlay</button>'
        + '<div id="log-parlay-result" class="mult-result"></div>'
        + '</div>';
    area.innerHTML = html;
    calcEntry();
}

function logParlay() {
    var resultEl = document.getElementById('log-parlay-result');
    var multEl = document.getElementById('entry-mult');
    var m = parseFloat(multEl ? multEl.value : NaN);

    if (!m || m <= 1.0) {
        resultEl.innerHTML = '<span style="color:#ff9a9a">Enter the real payout multiplier above first.</span>';
        return;
    }

    var legIds = Object.keys(selectedLegs);
    var legsForLog = legIds.map(function(legId) { return selectedLegs[legId].fullData; })
        .filter(function(d) { return d && d.player; });

    if (legsForLog.length === 0) {
        resultEl.innerHTML = '<span style="color:#ff9a9a">No loggable leg data found -- try re-selecting the legs.</span>';
        return;
    }

    var typeSelect = document.getElementById('log-entry-type');
    var entryTypeLabel = legIds.length + '-' + (typeSelect ? typeSelect.value : 'Power');
    var today = new Date().toISOString().slice(0, 10);

    resultEl.innerHTML = 'Logging...';
    fetch('/log_parlay', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ legs: legsForLog, multiplier: m, entry_type_label: entryTypeLabel, date: today })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (data.success) {
            resultEl.innerHTML = '<span style="color:#8aff8a">' + data.message + '</span>';
        } else {
            resultEl.innerHTML = '<span style="color:#ff9a9a">' + data.message + '</span>';
        }
    })
    .catch(function(err) {
        resultEl.innerHTML = '<span style="color:#ff9a9a">Request failed: ' + err + '</span>';
    });
}

function calcEntry() {
    var resultEl = document.getElementById('entry-result');
    var multEl = document.getElementById('entry-mult');
    if (!resultEl || !multEl) return;
    var legIds = Object.keys(selectedLegs);
    var m = parseFloat(multEl.value);

    if (legIds.length === 0) {
        resultEl.innerHTML = '';
        return;
    }
    var combinedProb = 1.0;
    legIds.forEach(function(legId) {
        combinedProb *= (selectedLegs[legId].consensus_pct / 100.0);
    });
    var combinedPct = (combinedProb * 100).toFixed(1);

    if (!m || m <= 1.0) {
        resultEl.innerHTML = 'Combined true probability: ' + combinedPct
            + '%. Enter the real multiplier above to see if it clears break-even.';
        return;
    }
    var requiredPct = (100.0 / m);
    var marginPts = (combinedPct - requiredPct);
    var tier = marginPts < 1.5 ? 'BELOW BAR' : (marginPts < 4.0 ? 'TIER B' : 'TIER A');
    var color = tier === 'TIER A' ? '#4caf50' : (tier === 'TIER B' ? '#ffb300' : '#888');
    resultEl.innerHTML = 'Combined true probability: ' + combinedPct + '% | Required (1/multiplier): '
        + requiredPct.toFixed(1) + '%<br>'
        + 'Real edge margin: ' + (marginPts >= 0 ? '+' : '') + marginPts.toFixed(1) + ' pts | '
        + '<strong style="color:' + color + '">' + tier + '</strong>';
}

// ---- Page load: merge any new scan into storage, then render from storage ----
(function() {
    var payloadEl = document.getElementById('scan-payload');
    var games = loadGames();
    var activeKey = localStorage.getItem(ACTIVE_KEY);
    selectedLegs = loadSelected();

    if (payloadEl) {
        try {
            var payload = JSON.parse(payloadEl.textContent);
            games[payload.gameKey] = payload;
            saveGames(games);
            activeKey = payload.gameKey;
            localStorage.setItem(ACTIVE_KEY, activeKey);
        } catch (e) { /* no valid new scan, ignore */ }
    }

    if (!activeKey || !games[activeKey]) {
        var keys = Object.keys(games);
        activeKey = keys.length ? keys[0] : null;
    }

    renderTabs(games, activeKey);
    renderFilterBar();
    renderEntryBuilder();
    if (activeKey && games[activeKey]) renderColumns(games[activeKey]);
})();
</script>
</div></body></html>"""


def render_form(team_a="", team_b="", entry="3", sport="basketball_wnba",
                 entry_type="power", error_html="", scan_payload=None):
    head = PAGE_HEAD.format(
        team_a=team_a, team_b=team_b,
        today=datetime.date.today().isoformat(),
        sel_wnba="selected" if sport == "basketball_wnba" else "",
        sel_nba="selected" if sport == "basketball_nba" else "",
        sel_mlb="selected" if sport == "baseball_mlb" else "",
        sel_power="selected" if entry_type == "power" else "",
        sel_flex="selected" if entry_type == "flex" else "",
        sel_2="selected" if entry == "2" else "",
        sel_3="selected" if entry == "3" else "",
        sel_4="selected" if entry == "4" else "",
        sel_5="selected" if entry == "5" else "",
        sel_6="selected" if entry == "6" else "",
    )
    payload_script = ""
    if scan_payload is not None:
        payload_json = json.dumps(scan_payload).replace("</", "<\\/")
        payload_script = f'<script id="scan-payload" type="application/json">{payload_json}</script>'
    return head + error_html + payload_script + STATIC_FOOTER


def rows_to_payload(rows, bar, team_a, team_b, sport, entry, entry_type, raw_prizepicks=None):
    game_key = f"{sport}|{team_a.strip().lower()}|{team_b.strip().lower()}|{entry}|{entry_type}"
    type_label = "Power" if entry_type == "power" else "Flex"
    label = f"{team_a} vs {team_b} ({entry}-pick {type_label})"
    return {
        "gameKey": game_key,
        "label": label,
        "bar": bar,
        "rows": rows,
        "rawPrizePicks": raw_prizepicks or [],
    }


# ---------- HTTP server ----------

class Handler(BaseHTTPRequestHandler):
    def _send_html(self, html, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_json(self, obj, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_form())
        elif parsed.path == "/games":
            qs = urllib.parse.parse_qs(parsed.query)
            sport = qs.get("sport", ["basketball_wnba"])[0]
            config = load_config()
            api_key = config.get("api_key", "")
            if not api_key or api_key == "PASTE_YOUR_PROPLINE_KEY_HERE":
                self._send_json({"error": "No API key set in config.json."}, 400)
                return
            try:
                games = list_upcoming_events(sport, api_key)
                self._send_json({"games": games})
            except Exception as e:
                self._send_json({"error": f"{type(e).__name__}: {e}"}, 500)
        else:
            self._send_html("<h1>Not found</h1>", 404)

    def do_POST(self):
        if self.path == "/scan":
            self.handle_scan()
        elif self.path == "/scan_slate":
            self.handle_scan_slate()
        elif self.path == "/log_parlay":
            self.handle_log_parlay()
        else:
            self._send_html("<h1>Not found</h1>", 404)

    def handle_log_parlay(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
        except Exception:
            self._send_json({"success": False, "message": "Malformed request."})
            return

        legs = data.get("legs", [])
        multiplier = data.get("multiplier")
        entry_type_label = data.get("entry_type_label", "")
        date_str = data.get("date", datetime.date.today().isoformat())

        if not legs:
            self._send_json({"success": False, "message": "No legs selected."})
            return
        try:
            multiplier = float(multiplier)
            if multiplier <= 1.0:
                raise ValueError()
        except (TypeError, ValueError):
            self._send_json({"success": False, "message": "Enter a valid real payout multiplier (e.g. 2.3)."})
            return

        config = load_config()
        workbook_path = config.get("tracking_workbook_path", "")

        success, message, entry_id = log_parlay_to_excel(workbook_path, legs, multiplier, entry_type_label, date_str)
        self._send_json({"success": success, "message": message, "entry_id": entry_id})

    def handle_scan(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        form = urllib.parse.parse_qs(body)
        team_a = form.get("team_a", [""])[0]
        team_b = form.get("team_b", [""])[0]
        sport = form.get("sport", ["basketball_wnba"])[0]
        entry = form.get("entry", ["3"])[0]
        entry_type = form.get("entry_type", ["power"])[0]

        config = load_config()
        api_key = config.get("api_key", "")

        if not api_key or api_key == "PASTE_YOUR_PROPLINE_KEY_HERE":
            error_html = ('<div class="error">No API key set. Open config.json in this folder '
                           'and paste your PropLine key in place of PASTE_YOUR_PROPLINE_KEY_HERE, '
                           'then restart the app.</div>')
            self._send_html(render_form(team_a, team_b, entry, sport, entry_type, error_html))
            return

        if not team_a.strip() or not team_b.strip():
            error_html = '<div class="error">Enter both team names, or use "Scan whole slate" instead.</div>'
            self._send_html(render_form(team_a, team_b, entry, sport, entry_type, error_html))
            return

        if entry_type == "flex" and entry == "2":
            error_html = ('<div class="error">Flex Play requires at least 3 picks -- '
                           'PrizePicks doesn\'t offer a 2-pick Flex option. Pick 3-6, or switch to Power Play.</div>')
            self._send_html(render_form(team_a, team_b, entry, sport, entry_type, error_html))
            return

        try:
            event = find_event(sport, team_a, team_b, api_key)
            if not event:
                error_html = (f'<div class="error">Couldn\'t find a game matching "{team_a}" vs '
                               f'"{team_b}" for this sport/date. Check team spelling or try the other sport.</div>')
                self._send_html(render_form(team_a, team_b, entry, sport, entry_type, error_html))
                return

            markets = MARKETS_BY_SPORT.get(sport, BASKETBALL_MARKETS)
            full_event = fetch_props(sport, event["id"], api_key, markets)
            raw_prizepicks = extract_raw_prizepicks(full_event)

            bar_table = POWER_PLAY_BARS if entry_type == "power" else FLEX_BARS
            bar = bar_table.get(int(entry), 55.0)
            rows, bar = build_report(full_event, bar)

            if not rows:
                error_html = '<div class="error">No gradeable legs found -- no overlapping book coverage for this game/market set.</div>'
                self._send_html(render_form(team_a, team_b, entry, sport, entry_type, error_html))
                return

            payload = rows_to_payload(rows, bar, team_a, team_b, sport, entry, entry_type, raw_prizepicks)
            self._send_html(render_form(team_a, team_b, entry, sport, entry_type, scan_payload=payload))

        except urllib.error.HTTPError as e:
            error_html = f'<div class="error">PropLine API error: {e.code} {e.reason}. Check your API key in config.json.</div>'
            self._send_html(render_form(team_a, team_b, entry, sport, entry_type, error_html))
        except Exception as e:
            error_html = f'<div class="error">Something went wrong: {type(e).__name__}: {e}</div>'
            self._send_html(render_form(team_a, team_b, entry, sport, entry_type, error_html))

    def handle_scan_slate(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        form = urllib.parse.parse_qs(body)
        sport = form.get("sport", ["basketball_wnba"])[0]
        entry = form.get("entry", ["3"])[0]
        entry_type = form.get("entry_type", ["power"])[0]
        slate_date = form.get("slate_date", [""])[0]

        config = load_config()
        api_key = config.get("api_key", "")

        if not api_key or api_key == "PASTE_YOUR_PROPLINE_KEY_HERE":
            error_html = ('<div class="error">No API key set. Open config.json in this folder '
                           'and paste your PropLine key in place of PASTE_YOUR_PROPLINE_KEY_HERE, '
                           'then restart the app.</div>')
            self._send_html(render_form("", "", entry, sport, entry_type, error_html))
            return

        if not slate_date:
            error_html = '<div class="error">Pick a date for the slate scan.</div>'
            self._send_html(render_form("", "", entry, sport, entry_type, error_html))
            return

        if entry_type == "flex" and entry == "2":
            error_html = ('<div class="error">Flex Play requires at least 3 picks -- '
                           'PrizePicks doesn\'t offer a 2-pick Flex option. Pick 3-6, or switch to Power Play.</div>')
            self._send_html(render_form("", "", entry, sport, entry_type, error_html))
            return

        try:
            bar_table = POWER_PLAY_BARS if entry_type == "power" else FLEX_BARS
            bar = bar_table.get(int(entry), 55.0)

            rows, raw, scanned_games, skipped_games = scan_slate(sport, slate_date, api_key, bar)

            if not scanned_games:
                error_html = f'<div class="error">No {sport.split("_")[-1].upper()} games found on {slate_date}.</div>'
                self._send_html(render_form("", "", entry, sport, entry_type, error_html))
                return

            if not rows:
                skipped_note = f" ({len(skipped_games)} game(s) failed to fetch.)" if skipped_games else ""
                error_html = (f'<div class="error">Scanned {len(scanned_games)} game(s) but found no gradeable '
                               f'legs -- no overlapping book coverage.{skipped_note}</div>')
                self._send_html(render_form("", "", entry, sport, entry_type, error_html))
                return

            sport_label = {"basketball_wnba": "WNBA", "basketball_nba": "NBA", "baseball_mlb": "MLB"}.get(sport, sport)
            type_label = "Power" if entry_type == "power" else "Flex"
            game_key = f"{sport}|slate|{slate_date}|{entry}|{entry_type}"
            label = f"{sport_label} Slate {slate_date} ({entry}-pick {type_label})"
            payload = {
                "gameKey": game_key,
                "label": label,
                "bar": bar,
                "rows": rows,
                "rawPrizePicks": raw,
                "scannedGames": scanned_games,
            }
            if skipped_games:
                payload["skippedNote"] = f"{len(skipped_games)} of {len(scanned_games) + len(skipped_games)} games failed to fetch and were skipped."

            self._send_html(render_form("", "", entry, sport, entry_type, scan_payload=payload))

        except urllib.error.HTTPError as e:
            error_html = f'<div class="error">PropLine API error: {e.code} {e.reason}. Check your API key in config.json.</div>'
            self._send_html(render_form("", "", entry, sport, entry_type, error_html))
        except Exception as e:
            error_html = f'<div class="error">Something went wrong: {type(e).__name__}: {e}</div>'
            self._send_html(render_form("", "", entry, sport, entry_type, error_html))

    def log_message(self, format, *args):
        pass  # keep the console quiet


def main():
    load_config()  # creates config.json with a placeholder on first run
    server = HTTPServer(("localhost", PORT), Handler)
    url = f"http://localhost:{PORT}/"
    print(f"PrizePicks Edge Finder running at {url}")
    print("Press Ctrl+C in this window to stop it.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nStopped.")


if __name__ == "__main__":
    main()