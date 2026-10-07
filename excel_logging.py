"""Spreadsheet logging -- appends scanned/selected legs to the tracking workbook."""

import datetime
import json
import os
import re
import shutil

from result_grading import build_tag, check_clv, check_result, parse_tag
from scoring import extract_consensus, poisson_binomial_dist

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

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
    "player_pass_yds": "PASS YDS", "player_pass_tds": "PASS TD", "player_pass_completions": "COMP",
    "player_pass_attempts": "PASS ATT", "player_pass_interceptions": "INT", "player_rush_yds": "RUSH YDS",
    "player_rush_attempts": "RUSH ATT", "player_receptions": "REC", "player_reception_yds": "REC YDS",
    "player_pass_rush_reception_yds": "PASS+RUSH+REC YDS", "player_kicking_points": "KICK PTS",
    "player_field_goals": "FG MADE", "player_anytime_td": "ANY TD",
}
LINE_TYPE_MAP = {"standard": "STD", "goblin": "GOBLIN", "demon": "DEMON"}
TIER_CODE_MAP = {"TIER S": "S", "TIER A": "A", "TIER B": "B", "TIER C": "C", "BELOW BAR": "BELOW BAR"}

# The Leg Log's column layout. Every read/write here (and in the two report
# modules) is positional, so open_workbook refuses a sheet whose header row
# doesn't match -- a column inserted by hand in Excel would otherwise make
# every later write land in the wrong column silently.
LEG_LOG_HEADERS = [
    "Date", "Entry ID", "Entry Type", "Multiplier", "Player", "Game", "Stat", "Side", "PP Line", "Whole #?",
    "Line Type", "Book Line", "Book Over", "Book Under", "Predicted True %", "Estimate Type", "Bar",
    "Margin (pts)", "Tier", "Actual Value", "Result", "Hit", "Brier", "CLV Favorable?", "Notes",
]
COL = {h: i + 1 for i, h in enumerate(LEG_LOG_HEADERS)}  # header -> 1-based column number
ENTRY_LOG_HEADERS = ["Date", "Entry ID", "Type", "Multiplier", "# Legs", "Modelled EV", "Stake",
                     "Result (W/L/Partial)", "Return", "Net", "Notes"]
ENTRY_COL = {h: i + 1 for i, h in enumerate(ENTRY_LOG_HEADERS)}
# Flex payouts for 1/2 misses, stashed in an Entry Log row's Notes at logging
# time so settle_entries can pay a Partial out correctly later.
_FLEX_TAG_RE = re.compile(r"\[pkflex:1miss=([\d.]*),2miss=([\d.]*)\]")
OPENPYXL_MISSING = ("openpyxl isn't installed. In Command Prompt run: pip install openpyxl "
                    "--break-system-packages , then restart the app.")


def open_workbook(workbook_path, need_entry_log=False):
    """(workbook, None) ready to use, or (None, user-facing error message)."""
    if not OPENPYXL_AVAILABLE:
        return None, OPENPYXL_MISSING
    if not workbook_path:
        return None, "No tracking workbook path set. Add \"tracking_workbook_path\" in config.json."
    if not os.path.exists(workbook_path):
        return None, f"Workbook not found at: {workbook_path}. Check the path in config.json."
    try:
        wb = openpyxl.load_workbook(workbook_path)
    except PermissionError:
        return None, "Couldn't open the workbook -- close it in Excel first, then try again."
    except Exception as e:
        return None, f"Couldn't open workbook: {type(e).__name__}: {e}"
    if "Leg Log" not in wb.sheetnames or (need_entry_log and "Entry Log" not in wb.sheetnames):
        return None, "Workbook is missing its 'Leg Log'/'Entry Log' sheets -- wrong file?"
    layouts = [("Leg Log", LEG_LOG_HEADERS)]
    if "Entry Log" in wb.sheetnames:
        layouts.append(("Entry Log", ENTRY_LOG_HEADERS))
    for sheet, expected in layouts:
        headers = [wb[sheet].cell(row=1, column=c).value for c in range(1, len(expected) + 1)]
        if headers != expected:
            bad = next(i for i, (a, b) in enumerate(zip(headers, expected)) if a != b)
            return None, (f"{sheet} column {bad + 1} is '{headers[bad]}', expected '{expected[bad]}'. "
                          "Were columns added or moved in Excel? Put them back so picks aren't written "
                          "to the wrong column.")
    return wb, None


def _pick_key(where, player, line, side):
    return where + (player, float(line) if isinstance(line, (int, float)) else line, str(side or "").upper())


def leg_key(leg_log, r):
    """What makes a Leg Log row the same pick as another: same game + market
    (from its [pk:...] tag), player, line and side. The same leg logged twice --
    tracking-only, then again inside a real entry -- shares a key, so reports
    can count it once."""
    tag = parse_tag(leg_log.cell(row=r, column=COL["Notes"]).value)
    where = ((tag["event_id"], tag["market"]) if tag else
             (leg_log.cell(row=r, column=COL["Date"]).value, leg_log.cell(row=r, column=COL["Stat"]).value))
    return _pick_key(where, leg_log.cell(row=r, column=COL["Player"]).value,
                     leg_log.cell(row=r, column=COL["PP Line"]).value, leg_log.cell(row=r, column=COL["Side"]).value)


def _payout_multiple(entry_type, multiplier, notes, misses):
    """Payout per 1 unit staked for an entry with this many missed legs."""
    if misses == 0:
        return multiplier
    if "flex" in str(entry_type).lower():
        m = _FLEX_TAG_RE.search(notes or "")
        tiers = {1: m.group(1), 2: m.group(2)} if m else {}
        return float(tiers.get(misses) or 0)
    return 0.0


def entry_outcomes(wb):
    """Every Entry Log row, worked out from its legs' W/L in the Leg Log:
    [{row, entry_id, modelled_ev, stake, status, result, payout}] where status is
      "settled" -- every leg W/L; result W/Partial/L, payout = return per 1 unit staked
      "pending" -- some leg still has no result
      "manual"  -- a leg pushed; PrizePicks re-prices the entry at the smaller
                   size, which this doesn't model, so fill that one in by hand
    """
    leg_log, entry_log = wb["Leg Log"], wb["Entry Log"]
    results = {}
    r = 2
    while leg_log.cell(row=r, column=COL["Player"]).value not in (None, ""):
        eid = leg_log.cell(row=r, column=COL["Entry ID"]).value
        if isinstance(eid, str) and eid.startswith("E"):
            results.setdefault(eid, []).append(leg_log.cell(row=r, column=COL["Result"]).value)
        r += 1

    outcomes = []
    r = 2
    while entry_log.cell(row=r, column=ENTRY_COL["Entry ID"]).value not in (None, ""):
        row = {h: entry_log.cell(row=r, column=c).value for h, c in ENTRY_COL.items()}
        legs = results.get(row["Entry ID"], [])
        out = {"row": r, "entry_id": row["Entry ID"], "modelled_ev": row["Modelled EV"],
               "stake": row["Stake"] if isinstance(row["Stake"], (int, float)) else None,
               "status": "pending", "result": None, "payout": None}
        if "PUSH" in legs:
            out["status"] = "manual"
        elif legs and all(x in ("W", "L") for x in legs):
            payout = _payout_multiple(row["Type"], float(row["Multiplier"] or 0), row["Notes"], legs.count("L"))
            if "L" not in legs:
                result = "W"
            else:
                result = "Partial" if payout > 0 else "L"
            out.update(status="settled", payout=payout, result=result)
        outcomes.append(out)
        r += 1
    return outcomes


def settle_entries(wb):
    """Fill Result (and Return, when a Stake is entered) for every Entry Log
    row whose legs are all graded and whose Result is still blank. Net is the
    sheet's own formula. Returns (settled, needs_manual)."""
    entry_log = wb["Entry Log"]
    settled = manual = 0
    for o in entry_outcomes(wb):
        if entry_log.cell(row=o["row"], column=ENTRY_COL["Result (W/L/Partial)"]).value not in (None, ""):
            continue  # already settled, or filled in by hand
        if o["status"] == "manual":
            manual += 1
        elif o["status"] == "settled":
            entry_log.cell(row=o["row"], column=ENTRY_COL["Result (W/L/Partial)"], value=o["result"])
            if o["stake"] is not None:
                entry_log.cell(row=o["row"], column=ENTRY_COL["Return"], value=round(o["stake"] * o["payout"], 2))
            settled += 1
    return settled, manual


def leg_prices_path(workbook_path):
    """leg_prices.jsonl beside the tracking workbook."""
    return os.path.join(os.path.dirname(os.path.abspath(workbook_path)), "leg_prices.jsonl")


def _append_price_records(workbook_path, records):
    """Append records to leg_prices.jsonl, one JSON object per line, each
    stamped with the time. Two kinds, joined on entry_id + player/market/point:
      "log"   -- every book's price when the leg was logged
      "close" -- every book's price once the game started (written by "check CLV")
    The workbook keeps one representative price per leg; this keeps them all,
    so book weighting / de-vig changes can be tested on real logged picks, and
    each book's logged price can be compared to the close (sharp books are
    already near it; soft ones move toward it). book_prices rows are
    [book, point, over, under]. Best-effort: a failure here never fails the
    caller, since the workbook is already saved."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        with open(leg_prices_path(workbook_path), "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(dict(record, at=now)) + "\n")
    except OSError:
        pass


def _save_leg_prices(workbook_path, logged):
    """"log" records for just-logged legs. logged: [(entry_id, leg dict)]."""
    _append_price_records(workbook_path, [{
        "kind": "log", "entry_id": entry_id,
        "sport": leg.get("sport", ""), "event_id": str(leg.get("event_id", "")),
        "market": leg.get("market", ""), "player": leg.get("player", ""),
        "point": leg.get("point"), "side": leg.get("side"), "dfs_type": leg.get("dfs_type"),
        "consensus_pct": leg.get("consensus_pct"), "estimate_type": leg.get("estimate_type"),
        "book_prices": leg.get("book_prices") or [],
    } for entry_id, leg in logged])


BACKUPS_KEPT = 14


def _backup_workbook_today(workbook_path):
    """Before the app's first write of the day, copy the workbook to
    backups/<name>-YYYY-MM-DD.xlsx beside it, keeping the newest BACKUPS_KEPT.
    openpyxl rewrites the whole file on every save and can drop Excel features
    it doesn't understand (charts, images, pivots), and a crash mid-save can
    corrupt it -- this is the undo. Best-effort: never blocks the write."""
    folder = os.path.join(os.path.dirname(os.path.abspath(workbook_path)), "backups")
    stem = os.path.splitext(os.path.basename(workbook_path))[0]
    target = os.path.join(folder, f"{stem}-{datetime.date.today().isoformat()}.xlsx")
    if os.path.exists(target):
        return
    try:
        os.makedirs(folder, exist_ok=True)
        shutil.copy2(workbook_path, target)
        old = sorted(f for f in os.listdir(folder) if f.startswith(stem + "-") and f.endswith(".xlsx"))
        for name in old[:-BACKUPS_KEPT]:
            os.remove(os.path.join(folder, name))
    except OSError:
        pass


def log_parlay_to_excel(workbook_path, legs, multiplier, entry_type_label, date_str,
                         is_flex=False, one_miss_multiplier=None, two_miss_multiplier=None, stake=None):
    """
    legs: list of dicts with player/market/point/side/dfs_type/consensus_pct/bar/margin/
          tier/whole_number/estimate_type/book_point/over_price/under_price/books/matchup/spread_pct

    is_flex + one_miss_multiplier/two_miss_multiplier: a Flex entry pays out
    at multiple hit-count tiers (e.g. a 4-pick Flex still pays on 3 of 4
    hit), unlike Power's true all-or-nothing. Modelled EV only reflects that
    correctly when these are given -- without them (Power, or a Flex logged
    before this existed), it falls back to the old all-or-nothing formula.
    stake, if given, goes in the Entry Log's Stake column so "check results"
    can fill in Return once every leg is graded (see settle_entries).
    Returns (success, message, entry_id).
    """
    wb, error = open_workbook(workbook_path, need_entry_log=True)
    if error:
        return False, error, None

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
    true_pcts = []  # for the multi-tier Flex EV calc below, needs each leg's own probability
    # Find the first genuinely empty row rather than blindly appending after
    # max_row -- the sheet has hundreds of pre-formatted template rows with
    # formulas already in place but no actual data, and we want to fill those
    # in order (reusing their existing formulas) instead of skipping past all
    # of them and starting a fresh block far below.
    next_row = 2
    while leg_log.cell(row=next_row, column=COL["Player"]).value not in (None, ""):
        next_row += 1
    legs_written = 0

    for leg in legs:
        stat = STAT_ABBREV.get(leg.get("market", ""), leg.get("market", "").upper())
        line_type = LINE_TYPE_MAP.get(leg.get("dfs_type", "standard"), "STD")
        true_pct = leg.get("consensus_pct", 0) / 100.0
        bar_val = leg.get("bar")
        bar_dec = bar_val / 100.0 if bar_val is not None else None  # UNKNOWN-tier legs have no real bar -- leave blank, don't fabricate 0%
        combined_prob *= true_pct
        true_pcts.append(true_pct)
        tier_code = TIER_CODE_MAP.get(leg.get("tier", ""), leg.get("tier", ""))

        note = f"Logged via Edge Finder app. Books: {', '.join(leg.get('books', []))}."
        if leg.get("spread_pct") is not None:
            note += f" Spread: {leg['spread_pct']}pts."
        else:
            note += " Single book."
        # Embed sport/event/market so a later "check results" pass can
        # re-fetch this exact game's box score directly -- see result_grading.py.
        note += " " + build_tag(leg.get("sport", ""), leg.get("event_id", ""), leg.get("market", ""))

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

    n = len(true_pcts)
    if is_flex and n >= 3:
        dist = poisson_binomial_dist(true_pcts)
        modelled_ev = dist[n] * multiplier
        if one_miss_multiplier:
            modelled_ev += dist[n - 1] * one_miss_multiplier
        if two_miss_multiplier:
            modelled_ev += dist[n - 2] * two_miss_multiplier
        modelled_ev = round(modelled_ev, 3)
    else:
        modelled_ev = round(combined_prob * multiplier, 3)
    next_entry_row = 2
    while entry_log.cell(row=next_entry_row, column=2).value not in (None, ""):  # column B = Entry ID
        next_entry_row += 1
    entry_row = next_entry_row
    entry_note = "Logged via Edge Finder app."
    if is_flex:
        entry_note += f" [pkflex:1miss={one_miss_multiplier or ''},2miss={two_miss_multiplier or ''}]"
    entry_values = [date_str, entry_id, entry_type_label, multiplier, legs_written,
                     modelled_ev, stake, None, None, None, entry_note]
    for col, val in enumerate(entry_values, start=1):
        entry_log.cell(row=entry_row, column=col, value=val)
    entry_log.cell(row=entry_row, column=4).number_format = '0.0\\x'
    if stake is not None:
        entry_log.cell(row=entry_row, column=ENTRY_COL["Stake"]).number_format = '"$"#,##0.00'

    try:
        _backup_workbook_today(workbook_path)
        wb.save(workbook_path)
    except PermissionError:
        return False, "Couldn't save -- the workbook is open in Excel. Close it and try again.", None
    except Exception as e:
        return False, f"Couldn't save workbook: {type(e).__name__}: {e}", None

    _save_leg_prices(workbook_path, [(entry_id, leg) for leg in legs])
    return True, f"Logged {legs_written} leg(s) as entry {entry_id}.", entry_id


def log_legs_for_tracking(workbook_path, legs, date_str):
    """Log legs individually for tier-accuracy tracking -- no real entry, no
    multiplier, just a record of each leg's tier/probability at the time it
    was logged. Writes to 'Leg Log' only (never 'Entry Log', since there's no
    combined real entry here). 'Actual Value'/'Result' stay blank exactly like
    log_parlay_to_excel's rows -- fill in W/L by hand once the game finishes,
    and the sheet's existing hit/squared-error formulas do the rest, so you
    can pivot hit-rate by Tier to see whether the tiers actually predict
    anything. IDs use a "T<n>" namespace (not "E<n>") so these rows are
    visually distinguishable from real placed entries in the spreadsheet.
    Returns (success, message).
    """
    wb, error = open_workbook(workbook_path)
    if error:
        return False, error

    leg_log = wb["Leg Log"]

    existing_ids = set()
    for row in leg_log.iter_rows(min_row=2, max_col=2, values_only=True):
        eid = row[1]
        if eid and isinstance(eid, str) and eid.startswith("T") and eid[1:].isdigit():
            existing_ids.add(int(eid[1:]))
    next_id_num = (max(existing_ids) + 1) if existing_ids else 1

    # Tracking-only rows exist just to measure the model, so a pick already in
    # the Leg Log (from any earlier log) would only be counted twice -- skip it.
    # log_parlay_to_excel doesn't skip: a real entry needs every one of its legs
    # to settle, and the reports de-duplicate by leg_key instead.
    seen = set()
    next_row = 2
    while leg_log.cell(row=next_row, column=COL["Player"]).value not in (None, ""):
        seen.add(leg_key(leg_log, next_row))
        next_row += 1
    legs_written = skipped = 0
    logged = []

    for leg in legs:
        key = _pick_key((str(leg.get("event_id", "")), leg.get("market", "")),
                        leg.get("player", ""), leg.get("point"), leg.get("side"))
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        stat = STAT_ABBREV.get(leg.get("market", ""), leg.get("market", "").upper())
        line_type = LINE_TYPE_MAP.get(leg.get("dfs_type", "standard"), "STD")
        true_pct = leg.get("consensus_pct", 0) / 100.0
        bar_val = leg.get("bar")
        bar_dec = bar_val / 100.0 if bar_val is not None else None  # UNKNOWN-tier legs have no real bar -- leave blank, don't fabricate 0%
        tier_code = TIER_CODE_MAP.get(leg.get("tier", ""), leg.get("tier", ""))
        entry_id = f"T{next_id_num}"
        next_id_num += 1

        note = f"Tracking-only, not a real placed entry -- logged via Edge Finder app. Books: {', '.join(leg.get('books', []))}."
        if leg.get("spread_pct") is not None:
            note += f" Spread: {leg['spread_pct']}pts."
        else:
            note += " Single book."
        note += " " + build_tag(leg.get("sport", ""), leg.get("event_id", ""), leg.get("market", ""))

        r = next_row
        values = [
            date_str, entry_id, "TRACKING", None,
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
        leg_log.cell(row=next_row, column=15).number_format = '0.0%'
        leg_log.cell(row=next_row, column=17).number_format = '0.0%'
        leg_log.cell(row=next_row, column=18).number_format = '0.0%'
        leg_log.cell(row=next_row, column=23).number_format = '0.0000'
        next_row += 1
        legs_written += 1
        logged.append((entry_id, leg))

    skipped_note = f" Skipped {skipped} already in the log." if skipped else ""
    if not legs_written:
        return True, f"Nothing new to log.{skipped_note}"

    try:
        _backup_workbook_today(workbook_path)
        wb.save(workbook_path)
    except PermissionError:
        return False, "Couldn't save -- the workbook is open in Excel. Close it and try again."
    except Exception as e:
        return False, f"Couldn't save workbook: {type(e).__name__}: {e}"

    _save_leg_prices(workbook_path, logged)
    return True, f"Logged {legs_written} leg(s) for tracking (no multiplier -- fill in Result later).{skipped_note}"


def check_and_fill_results(workbook_path, api_key):
    """Scan 'Leg Log' for rows with a blank Result but real leg data, re-fetch
    each one's real box score via the [pk:sport=...,event=...,market=...] tag
    embedded in its Note column at logging time (see build_tag in
    result_grading.py), and fill in Actual Value/Result where the game has
    finished. Rows logged before this tag existed, or where the game hasn't
    finished yet, are left alone -- counted separately so the caller can
    report what happened rather than silently doing nothing for them.
    Returns (success, message).
    """
    wb, error = open_workbook(workbook_path)
    if error:
        return False, error

    leg_log = wb["Leg Log"]
    stats_cache = {}  # (sport, event_id) -> box score, shared across every row this pass
    graded = pending = no_data = no_tag = 0
    changed = False

    row = 2
    while leg_log.cell(row=row, column=COL["Player"]).value not in (None, ""):
        player = leg_log.cell(row=row, column=COL["Player"]).value
        if leg_log.cell(row=row, column=COL["Result"]).value not in (None, ""):
            row += 1
            continue  # already graded, or filled in by hand -- leave it alone

        tag = parse_tag(leg_log.cell(row=row, column=COL["Notes"]).value)
        if not tag:
            no_tag += 1
            row += 1
            continue

        side = "More" if str(leg_log.cell(row=row, column=COL["Side"]).value or "").upper() == "MORE" else "Less"
        point = leg_log.cell(row=row, column=COL["PP Line"]).value

        try:
            status, result, actual_value = check_result(
                tag["sport"], tag["event_id"], tag["market"], player, point, side, api_key, stats_cache)
        except Exception:
            pending += 1  # API hiccup for this one -- try again next pass, don't fail the whole run
            row += 1
            continue

        if status != "final":
            pending += 1
        elif result is None:
            no_data += 1
        else:
            leg_log.cell(row=row, column=COL["Actual Value"], value=actual_value)
            leg_log.cell(row=row, column=COL["Result"], value=result)
            graded += 1
            changed = True
        row += 1

    settled = manual = 0
    if "Entry Log" in wb.sheetnames:
        settled, manual = settle_entries(wb)
        changed = changed or settled > 0

    if changed:
        try:
            _backup_workbook_today(workbook_path)
            wb.save(workbook_path)
        except PermissionError:
            return False, "Couldn't save -- the workbook is open in Excel. Close it and try again."
        except Exception as e:
            return False, f"Couldn't save workbook: {type(e).__name__}: {e}"

    message = (f"Graded {graded} pick(s). {pending} still pending (game not finished yet). "
               f"{no_data} finished but couldn't match the player/stat. "
               f"{no_tag} too old to auto-check (logged before this feature existed).")
    if settled:
        message += f" Settled {settled} entry(s)."
    if manual:
        message += f" {manual} entry(s) had a pushed leg -- fill in Result by hand."
    return True, message


def check_and_fill_clv(workbook_path, api_key):
    """Scan 'Leg Log' for rows with a blank 'CLV Favorable?' column, and fill
    it in once the game has started -- unlike check_and_fill_results, this
    does NOT wait for the game to finish, since lines lock at kickoff and CLV
    is knowable as soon as the market closes. Uses the same [pk:...] tag in
    the Note column as check_and_fill_results. Returns (success, message).
    """
    wb, error = open_workbook(workbook_path)
    if error:
        return False, error

    leg_log = wb["Leg Log"]
    cache = {}  # (sport, event_id, "stats"|"odds", ...) -> fetched data, shared across every row this pass
    checked = pending = no_line = no_tag = 0
    changed = False
    closes = []

    row = 2
    while leg_log.cell(row=row, column=COL["Player"]).value not in (None, ""):
        if leg_log.cell(row=row, column=COL["CLV Favorable?"]).value not in (None, ""):
            row += 1
            continue  # already checked, or filled in by hand -- leave it alone

        tag = parse_tag(leg_log.cell(row=row, column=COL["Notes"]).value)
        if not tag:
            no_tag += 1
            row += 1
            continue

        player = leg_log.cell(row=row, column=COL["Player"]).value
        side = "More" if str(leg_log.cell(row=row, column=COL["Side"]).value or "").upper() == "MORE" else "Less"
        point = leg_log.cell(row=row, column=COL["PP Line"]).value

        try:
            status, favorable, _closing_point = check_clv(
                tag["sport"], tag["event_id"], tag["market"], player, point, side, api_key, cache)
        except Exception:
            pending += 1  # API hiccup for this one -- try again next pass, don't fail the whole run
            row += 1
            continue

        if status == "upcoming":
            pending += 1
            row += 1
            continue
        if favorable is None:
            no_line += 1
        else:
            leg_log.cell(row=row, column=COL["CLV Favorable?"], value=("YES" if favorable else "NO"))
            checked += 1
            changed = True
        # Every book's closing price at this leg's line, from the odds check_clv
        # just fetched (cached, no extra request). Written even when the line
        # didn't move (favorable None) -- those rows get re-checked next run, so
        # a leg can collect several "close" records; the first one is the close.
        closing_event = cache.get((tag["sport"], tag["event_id"], "odds", tag["market"]))
        if closing_event:
            closes.append({
                "kind": "close", "entry_id": leg_log.cell(row=row, column=COL["Entry ID"]).value,
                "sport": tag["sport"], "event_id": tag["event_id"], "market": tag["market"],
                "player": player, "point": point, "side": side, "closing_point": _closing_point,
                "book_prices": [[c["book"], c["book_point"], c["over_price"], c["under_price"]]
                                for c in extract_consensus(closing_event, player, tag["market"], point)],
            })
        row += 1

    if changed:
        try:
            _backup_workbook_today(workbook_path)
            wb.save(workbook_path)
        except PermissionError:
            return False, "Couldn't save -- the workbook is open in Excel. Close it and try again."
        except Exception as e:
            return False, f"Couldn't save workbook: {type(e).__name__}: {e}"

    _append_price_records(workbook_path, closes)
    message = (f"Checked CLV for {checked} pick(s). {pending} still pending (game hasn't started yet). "
               f"{no_line} started but no current consensus line was found. "
               f"{no_tag} too old to auto-check (logged before this feature existed).")
    return True, message
