"""HTTP server: routes requests to the scan/slate/log handlers and serves the
static frontend assets (templates/page.html, static/style.css, static/app.js)."""

import datetime
import html
import json
import os
import socket
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ai_context import check_context, check_correlation
from auth import (
    SESSION_MAX_AGE, create_session, create_user, destroy_session, parse_session_cookie, username_for_session,
    verify_user,
)
from calibration_report import build_report as build_calibration_report
from config import load_config, propline_key
from correlation_report import build_report as build_correlation_report
from excel_logging import check_and_fill_clv, check_and_fill_results, log_legs_for_tracking, log_parlay_to_excel
from goblin_demon_calibration import estimate_multiplier, record_correction
from propline_api import fetch_props, list_upcoming_events, scan_slate, utc_to_local_date_str
from scoring import (
    BASKETBALL_MARKETS, DEFAULT_BAR, MARKETS_BY_SPORT, SPORT_LABELS,
    STANDARD_2PICK_LEG_MULTIPLIER, build_report, extract_pp_lines, extract_raw_all_books,
    cap_tier, find_consensus_reference_point, grade_leg, grade_manual_leg,
)
from views import render_form, render_home, render_login, render_register, rows_to_payload

PORT = 8787
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Explicit allowlist of servable static files -- avoids any path-traversal
# risk from turning request paths directly into filesystem paths.
STATIC_FILES = {
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
}

# Requests run on their own threads (a slow scan shouldn't freeze the app), so
# handlers that write shared files (users.json, calibration JSON, the Excel
# workbook) take this lock to keep two writes from interleaving.
# ponytail: one global lock, per-file locks if check_results starts blocking logging.
WRITE_LOCK = threading.Lock()

# The server listens on the whole LAN, so throttle password guessing: after
# LOGIN_MAX_FAILURES wrong passwords from one IP inside LOGIN_WINDOW seconds,
# refuse further attempts from it until the oldest failure ages out.
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW = 15 * 60
_login_failures = {}  # ip -> [failure timestamps]
_login_lock = threading.Lock()

MAX_BODY_BYTES = 2_000_000  # far above any real request (a big entry log is a few KB)


def _login_blocked(ip):
    now = time.time()
    with _login_lock:
        recent = [t for t in _login_failures.get(ip, []) if now - t < LOGIN_WINDOW]
        _login_failures[ip] = recent
        return len(recent) >= LOGIN_MAX_FAILURES


def _record_login_failure(ip):
    with _login_lock:
        _login_failures.setdefault(ip, []).append(time.time())


class Handler(BaseHTTPRequestHandler):
    # The client (browser tab closed, navigated away, request cancelled) can
    # drop the connection while a response is being written -- that's normal
    # and not a bug in the request logic, so swallow it instead of letting
    # http.server dump a scary traceback to the console for every occurrence.
    _DISCONNECT_ERRORS = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)

    def _send_html(self, html, status=200):
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except self._DISCONNECT_ERRORS:
            pass

    def _send_json(self, obj, status=200):
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(obj).encode("utf-8"))
        except self._DISCONNECT_ERRORS:
            pass

    def _send_static(self, filename, content_type):
        with open(os.path.join(STATIC_DIR, filename), "rb") as f:
            data = f.read()
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except self._DISCONNECT_ERRORS:
            pass

    def _send_redirect(self, location, set_cookie=None):
        try:
            self.send_response(303)
            self.send_header("Location", location)
            if set_cookie:
                self.send_header("Set-Cookie", set_cookie)
            self.end_headers()
        except self._DISCONNECT_ERRORS:
            pass

    def _session_cookie(self, token):
        return f"session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_MAX_AGE}"

    def _current_user(self):
        token = parse_session_cookie(self.headers.get("Cookie", ""))
        return username_for_session(token) if token else None

    def _read_body(self):
        """Request body, or "" when Content-Length is missing, garbage, or huge --
        callers already treat an empty body as a malformed/incomplete request."""
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return ""
        if not 0 < length <= MAX_BODY_BYTES:
            return ""
        return self.rfile.read(length).decode("utf-8", errors="replace")

    def _read_form(self):
        return urllib.parse.parse_qs(self._read_body())

    def _read_json(self):
        """Request body as a dict, or None after already sending a malformed-request reply."""
        try:
            data = json.loads(self._read_body())
        except ValueError:
            data = None
        if not isinstance(data, dict):
            self._send_json({"success": False, "message": "Malformed request."})
            return None
        return data

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path in STATIC_FILES:
            filename, content_type = STATIC_FILES[parsed.path]
            self._send_static(filename, content_type)
            return

        user = self._current_user()

        if parsed.path == "/login":
            self._send_redirect("/") if user else self._send_html(render_login())
            return
        if parsed.path == "/register":
            self._send_redirect("/") if user else self._send_html(render_register())
            return
        if parsed.path == "/logout":
            token = parse_session_cookie(self.headers.get("Cookie", ""))
            if token:
                destroy_session(token)
            self._send_redirect("/login", set_cookie="session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0")
            return

        if not user:
            if parsed.path in ("/games", "/calibration_report", "/correlation_report"):
                self._send_json({"error": "Not logged in."}, 401)
            else:
                self._send_redirect("/login")
            return

        if parsed.path == "/":
            self._send_html(render_home(user))
        elif parsed.path == "/app":
            self._send_html(render_form())
        elif parsed.path == "/games":
            qs = urllib.parse.parse_qs(parsed.query)
            sport = qs.get("sport", [""])[0]
            date_str = qs.get("date", [""])[0]
            if not sport:
                self._send_json({"games": []})
                return
            config = load_config()
            api_key = propline_key(config)
            if not api_key:
                self._send_json({"error": "No API key set in config.json."}, 400)
                return
            try:
                games = list_upcoming_events(sport, api_key)
                if date_str:
                    # 3-day window, not an exact match -- most sports don't play
                    # every day, so a single-date filter often shows nothing.
                    try:
                        start = datetime.date.fromisoformat(date_str)
                    except ValueError:
                        start = None
                    if start:
                        end = (start + datetime.timedelta(days=2)).isoformat()
                        start = start.isoformat()
                        games = [g for g in games
                                 if start <= utc_to_local_date_str(g.get("commence_time")) <= end]
                self._send_json({"games": games})
            except Exception as e:
                self._send_json({"error": f"{type(e).__name__}: {e}"}, 500)
        elif parsed.path == "/calibration_report":
            config = load_config()
            workbook_path = config.get("tracking_workbook_path", "")
            success, message, data = build_calibration_report(workbook_path)
            self._send_json({"success": success, "message": message, "data": data})
        elif parsed.path == "/correlation_report":
            config = load_config()
            workbook_path = config.get("tracking_workbook_path", "")
            success, message, data = build_correlation_report(workbook_path)
            self._send_json({"success": success, "message": message, "data": data})
        else:
            self._send_html("<h1>Not found</h1>", 404)

    def do_POST(self):
        if self.path == "/login":
            self.handle_login()
            return
        if self.path == "/register":
            with WRITE_LOCK:
                self.handle_register()
            return

        if not self._current_user():
            if self.path in ("/scan", "/scan_slate"):
                self._send_redirect("/login")
            else:
                self._send_json({"success": False, "message": "Not logged in."}, 401)
            return

        if self.path == "/scan":
            self.handle_scan()
        elif self.path == "/scan_slate":
            self.handle_scan_slate()
        elif self.path in ("/log_parlay", "/log_tracking", "/check_results", "/check_clv", "/calibrate"):
            with WRITE_LOCK:
                getattr(self, "handle_" + self.path[1:])()
        elif self.path == "/grade_manual":
            self.handle_grade_manual()
        elif self.path == "/check_context":
            self.handle_check_context()
        elif self.path == "/check_correlation":
            self.handle_check_correlation()
        else:
            self._send_html("<h1>Not found</h1>", 404)

    def handle_login(self):
        ip = self.client_address[0]
        if _login_blocked(ip):
            self._send_html(render_login('<div class="error">Too many wrong passwords. '
                                         'Wait 15 minutes and try again.</div>'), 429)
            return

        form = self._read_form()
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]

        if not verify_user(username, password):
            _record_login_failure(ip)
            self._send_html(render_login('<div class="error">Wrong username or password.</div>'))
            return

        token = create_session(username.strip())
        self._send_redirect("/", set_cookie=self._session_cookie(token))

    def handle_register(self):
        form = self._read_form()
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]
        confirm = form.get("confirm", [""])[0]

        if password != confirm:
            self._send_html(render_register('<div class="error">Passwords don\'t match.</div>'))
            return

        ok, message = create_user(username, password)
        if not ok:
            self._send_html(render_register(f'<div class="error">{html.escape(message)}</div>'))
            return

        token = create_session(username.strip())
        self._send_redirect("/", set_cookie=self._session_cookie(token))

    def handle_calibrate(self):
        data = self._read_json()
        if data is None:
            return

        market = data.get("market")
        dfs_type = data.get("dfs_type")
        deviation = data.get("deviation")
        consensus_pct = data.get("consensus_pct")

        if dfs_type not in ("goblin", "demon") or not market or deviation is None:
            self._send_json({"success": False, "message": "Missing market/dfs_type/deviation."})
            return
        try:
            multiplier = float(data.get("multiplier"))
            if multiplier <= 1.0:
                raise ValueError()
        except (TypeError, ValueError):
            self._send_json({"success": False, "message": "Enter a valid real 2-pick total multiplier (e.g. 2.4)."})
            return

        record_correction(market, dfs_type, float(deviation), multiplier)

        assumed_multiplier = estimate_multiplier(market, dfs_type, float(deviation), STANDARD_2PICK_LEG_MULTIPLIER)
        result = {"success": True, "message": "Calibration saved.",
                  "assumed_multiplier": round(assumed_multiplier, 2) if assumed_multiplier else None}
        if consensus_pct is not None and assumed_multiplier:
            bar = 100.0 / assumed_multiplier
            margin, tier = grade_leg(bar, float(consensus_pct))
            tier = cap_tier(tier, bool(data.get("single_book")))
            result.update({"bar": round(bar, 1), "margin": round(margin, 1), "tier": tier})
        self._send_json(result)

    def handle_grade_manual(self):
        """Grade a hand-entered line PropLine doesn't carry -- e.g. a PrizePicks
        promo/discount pick -- against real consensus books, the same way any
        scanned leg gets graded. Used for one-off picks that don't show up
        through the normal scan/slate flow."""
        data = self._read_json()
        if data is None:
            return

        sport = data.get("sport") or ""
        event_id = data.get("event_id") or ""
        player = (data.get("player") or "").strip()
        market = (data.get("market") or "").strip()
        dfs_type = data.get("dfs_type") or "standard"
        point = data.get("point")

        if not sport or not event_id:
            self._send_json({"success": False, "message": "No game selected -- pick a single game's tab first."})
            return
        if not player or not market:
            self._send_json({"success": False, "message": "Enter both a player name and a market."})
            return
        try:
            point = float(point)
        except (TypeError, ValueError):
            self._send_json({"success": False, "message": "Enter a valid line (e.g. 62.5)."})
            return
        if dfs_type not in ("standard", "goblin", "demon", "discount"):
            dfs_type = "standard"

        config = load_config()
        api_key = propline_key(config)
        if not api_key:
            self._send_json({"success": False, "message": "No API key set in config.json."})
            return

        try:
            markets = MARKETS_BY_SPORT.get(sport, BASKETBALL_MARKETS)
            if market not in markets:
                markets = markets + [market]
            full_event = fetch_props(sport, event_id, api_key, markets)
        except urllib.error.HTTPError as e:
            self._send_json({"success": False, "message": f"PropLine API error: {e.code} {e.reason}."})
            return
        except Exception as e:
            self._send_json({"success": False, "message": f"{type(e).__name__}: {e}"})
            return

        player = _feed_spelling(full_event, player)
        row = grade_manual_leg(full_event, player, market, point, dfs_type, DEFAULT_BAR)
        # _grade_leg never returns None any more -- an ungradeable leg comes back
        # as a NO DATA row. Don't add one of those silently: say why, and tell a
        # name mismatch (books have nothing for this player) apart from a line
        # the books just don't reach (they list the player at a different line).
        if row is None or row.get("consensus_pct") is None:
            book_line = find_consensus_reference_point(full_event, player, market)
            if book_line is None:
                message = (f"No sportsbook lists {player} for this stat in this game. Check the name matches "
                           "the sportsbook spelling exactly (e.g. accents, Jr.), and that it's the right game.")
            else:
                message = (f"Books have {player} at {book_line:g}, but nothing at {point:g}, and no alt-line "
                           "ladder covers it, so there's no real probability to grade this line against.")
            self._send_json({"success": False, "message": message})
            return

        row["manual"] = True
        row["eventId"] = event_id
        row["sport"] = sport
        self._send_json({"success": True, "row": row})

    def handle_check_context(self):
        """Advisory-only research on one leg (recent performance, matchup
        history, home/away, injury status) via Tavily search + Groq. Never
        touches consensus_pct/bar/tier -- see ai_context.py for why that's a
        deliberate boundary, not an oversight."""
        data = self._read_json()
        if data is None:
            return

        config = load_config()
        tavily_key = config.get("tavily_api_key", "")
        groq_key = config.get("groq_api_key", "")

        success, text = check_context(
            player=data.get("player", ""),
            matchup=data.get("matchup", ""),
            sport=data.get("sport", ""),
            market_label=data.get("market_label", ""),
            side=data.get("side", ""),
            point=data.get("point"),
            tavily_key=tavily_key,
            groq_key=groq_key,
        )
        self._send_json({"success": success, "text": text})

    def handle_check_correlation(self):
        """Advisory-only correlation check across a built entry's legs via
        Tavily search + Groq. Flags relationships in plain language; never
        recalculates the entry's combined probability."""
        data = self._read_json()
        if data is None:
            return

        config = load_config()
        tavily_key = config.get("tavily_api_key", "")
        groq_key = config.get("groq_api_key", "")
        legs = data.get("legs", [])

        success, text = check_correlation(legs, tavily_key, groq_key)
        self._send_json({"success": success, "text": text})

    def handle_log_parlay(self):
        data = self._read_json()
        if data is None:
            return

        legs = data.get("legs", [])
        multiplier = data.get("multiplier")
        entry_type_label = data.get("entry_type_label", "")
        date_str = data.get("date", datetime.date.today().isoformat())
        is_flex = bool(data.get("is_flex"))
        one_miss_multiplier = data.get("one_miss_multiplier")
        two_miss_multiplier = data.get("two_miss_multiplier")

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
        try:
            one_miss_multiplier = float(one_miss_multiplier) if one_miss_multiplier is not None else None
        except (TypeError, ValueError):
            one_miss_multiplier = None
        try:
            two_miss_multiplier = float(two_miss_multiplier) if two_miss_multiplier is not None else None
        except (TypeError, ValueError):
            two_miss_multiplier = None
        try:
            stake = float(data.get("stake"))
            stake = stake if stake > 0 else None
        except (TypeError, ValueError):
            stake = None  # optional -- blank just means no dollar tracking for this entry

        config = load_config()
        workbook_path = config.get("tracking_workbook_path", "")

        success, message, entry_id = log_parlay_to_excel(
            workbook_path, legs, multiplier, entry_type_label, date_str,
            is_flex=is_flex, one_miss_multiplier=one_miss_multiplier, two_miss_multiplier=two_miss_multiplier,
            stake=stake)
        self._send_json({"success": success, "message": message, "entry_id": entry_id})

    def handle_log_tracking(self):
        """Log legs individually for tier-accuracy tracking -- no real entry
        or multiplier needed, just a record of what the model liked so you
        can fill in W/L later and check whether tiers actually predict hit
        rate."""
        data = self._read_json()
        if data is None:
            return

        legs = data.get("legs", [])
        date_str = data.get("date", datetime.date.today().isoformat())

        if not legs:
            self._send_json({"success": False, "message": "No legs selected."})
            return

        config = load_config()
        workbook_path = config.get("tracking_workbook_path", "")

        success, message = log_legs_for_tracking(workbook_path, legs, date_str)
        self._send_json({"success": success, "message": message})

    def handle_check_results(self):
        """Re-check every pending logged pick (real entries and tracking-only
        alike) against real box scores and fill in W/L for whichever games
        have finished since they were logged."""
        config = load_config()
        api_key = propline_key(config)
        workbook_path = config.get("tracking_workbook_path", "")

        if not api_key:
            self._send_json({"success": False, "message": "No API key set in config.json."})
            return

        success, message = check_and_fill_results(workbook_path, api_key)
        self._send_json({"success": success, "message": message})

    def handle_check_clv(self):
        """Check closing line value for every logged pick whose game has
        started -- unlike handle_check_results, doesn't wait for the game to
        finish, since lines lock at kickoff and CLV is knowable right away."""
        config = load_config()
        api_key = propline_key(config)
        workbook_path = config.get("tracking_workbook_path", "")

        if not api_key:
            self._send_json({"success": False, "message": "No API key set in config.json."})
            return

        success, message = check_and_fill_clv(workbook_path, api_key)
        self._send_json({"success": success, "message": message})

    def handle_scan(self):
        form = self._read_form()
        event_id = form.get("event_id", [""])[0]
        team_a = form.get("team_a", [""])[0]
        team_b = form.get("team_b", [""])[0]
        sport = form.get("sport", [""])[0]
        commence_time = form.get("commence_time", [""])[0]

        config = load_config()
        api_key = propline_key(config)

        if not api_key:
            error_html = ('<div class="error">No API key set. Open config.json in this folder '
                           'and paste your PropLine key in place of PASTE_YOUR_PROPLINE_KEY_HERE, '
                           'then restart the app.</div>')
            self._send_html(render_form(sport, error_html))
            return

        if not sport or not event_id:
            error_html = '<div class="error">Pick a sport and a game from the list first.</div>'
            self._send_html(render_form(sport, error_html))
            return

        try:
            markets = MARKETS_BY_SPORT.get(sport, BASKETBALL_MARKETS)
            full_event = fetch_props(sport, event_id, api_key, markets)
            raw_books = extract_raw_all_books(full_event)
            # A normal single game's raw-books dump is small (~500KB) and worth keeping
            # for the debug "Show raw data" panel. An unusually heavy prime-time game
            # (many books, 1000+ market blocks) can blow that up past 2MB -- the same
            # localStorage-bloat problem slate scans hit, just triggered by one big game
            # instead of many small ones. Drop it past a size threshold rather than
            # unconditionally, same tradeoff as scan_slate's include_raw=False but only
            # where it's actually needed.
            if len(json.dumps(raw_books)) > 750_000:
                raw_books = []

            rows, bar = build_report(full_event, DEFAULT_BAR)
            for r in rows:
                r["eventId"] = event_id
                r["sport"] = sport

            if not rows:
                error_html = f'<div class="error">{_no_legs_message(1, bool(extract_pp_lines(full_event)))}</div>'
                self._send_html(render_form(sport, error_html))
                return

            payload = rows_to_payload(rows, bar, event_id, team_a, team_b, sport, raw_books, markets)
            payload["commence"] = commence_time
            self._send_html(render_form(sport, scan_payload=payload))

        except urllib.error.HTTPError as e:
            error_html = f'<div class="error">PropLine API error: {e.code} {html.escape(str(e.reason))}. Check your API key in config.json.</div>'
            self._send_html(render_form(sport, error_html))
        except Exception as e:
            error_html = f'<div class="error">Something went wrong: {html.escape(f"{type(e).__name__}: {e}")}</div>'
            self._send_html(render_form(sport, error_html))

    def handle_scan_slate(self):
        form = self._read_form()
        sport = form.get("sport", [""])[0]
        slate_date = form.get("slate_date", [""])[0]

        config = load_config()
        api_key = propline_key(config)

        if not api_key:
            error_html = ('<div class="error">No API key set. Open config.json in this folder '
                           'and paste your PropLine key in place of PASTE_YOUR_PROPLINE_KEY_HERE, '
                           'then restart the app.</div>')
            self._send_html(render_form(sport, error_html))
            return

        if not sport:
            error_html = '<div class="error">Pick a sport for the slate scan.</div>'
            self._send_html(render_form(sport, error_html))
            return

        if not slate_date:
            error_html = '<div class="error">Pick a date for the slate scan.</div>'
            self._send_html(render_form(sport, error_html))
            return

        try:
            bar = DEFAULT_BAR
            rows, raw, scanned_games, skipped_games, scanned_game_events, any_prizepicks_board = scan_slate(
                sport, slate_date, api_key, bar, include_raw=False)

            if not scanned_games:
                error_html = f'<div class="error">No {sport.split("_")[-1].upper()} games found on {slate_date}.</div>'
                self._send_html(render_form(sport, error_html))
                return

            if not rows:
                skipped_note = f" ({len(skipped_games)} game(s) failed to fetch.)" if skipped_games else ""
                error_html = (f'<div class="error">{_no_legs_message(len(scanned_games), any_prizepicks_board)}'
                              f'{skipped_note}</div>')
                self._send_html(render_form(sport, error_html))
                return

            sport_label = SPORT_LABELS.get(sport, sport)
            game_key = f"{sport}|slate|{slate_date}"
            label = f"{sport_label} Slate {slate_date}"
            payload = {
                "gameKey": game_key,
                "label": label,
                "bar": bar,
                "rows": rows,
                "rawBooks": raw,
                "scannedGames": scanned_games,
                "sport": sport,
                "gameEvents": scanned_game_events,
                "availableMarkets": MARKETS_BY_SPORT.get(sport, BASKETBALL_MARKETS),
            }
            if skipped_games:
                payload["skippedNote"] = f"{len(skipped_games)} of {len(scanned_games) + len(skipped_games)} games failed to fetch and were skipped."

            self._send_html(render_form(sport, scan_payload=payload))

        except urllib.error.HTTPError as e:
            error_html = f'<div class="error">PropLine API error: {e.code} {html.escape(str(e.reason))}. Check your API key in config.json.</div>'
            self._send_html(render_form(sport, error_html))
        except Exception as e:
            error_html = f'<div class="error">Something went wrong: {html.escape(f"{type(e).__name__}: {e}")}</div>'
            self._send_html(render_form(sport, error_html))

    def log_message(self, format, *args):
        pass  # keep the console quiet


def _no_legs_message(n_games, any_prizepicks_board):
    """Why a scan came back empty, worded for its two real causes. Blames the
    odds feed, not PrizePicks: PrizePicks can have a board up that PropLine
    doesn't carry (e.g. NBA preseason, listed under PrizePicks' own "NBAP" league)."""
    games = "this game" if n_games == 1 else f"{n_games} games"
    if not any_prizepicks_board:
        return (f"Scanned {games}, but the odds feed (PropLine) has no PrizePicks lines for them. Either "
                "PrizePicks hasn't posted yet (try nearer game time), or its board for these games isn't in "
                "the feed. NBA preseason, listed under PrizePicks' NBAP tab, is one example.")
    return (f"Scanned {games}. PrizePicks lines were found, but no sportsbook (DraftKings, FanDuel, etc.) "
            "has props at those lines yet, so there's nothing to grade them against. Try again closer to "
            "game time, when more books post.")


def _name_key(name):
    """Name compared loosely: no accents, case, punctuation or spacing."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(ch for ch in plain.lower() if ch.isalnum())


def _feed_spelling(event, typed):
    """The sportsbook feed's own spelling of a hand-typed player name
    ("aja wilson" -> "A'ja Wilson"), since grading matches names exactly.
    Returns the typed name unchanged when nothing in the feed matches."""
    key = _name_key(typed)
    for book in event.get("bookmakers", []):
        for market in book.get("markets", []):
            for outcome in market.get("outcomes", []):
                name = outcome.get("description")
                if name and _name_key(name) == key:
                    return name
    return typed


def _lan_ip():
    """Best-effort LAN IP for the phone-access hint below. Doesn't actually
    send anything -- just asks the OS which local interface it would use to
    reach the internet, which is normally the real WiFi/ethernet address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def main():
    load_config()  # creates config.json with a placeholder on first run
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)  # not "localhost" -- reachable from other devices on the network, gated by login
    url = f"http://localhost:{PORT}/"
    print(f"PickKing running at {url}")
    lan_ip = _lan_ip()
    if lan_ip:
        print(f"On your phone (same WiFi): http://{lan_ip}:{PORT}/")
    print("Press Ctrl+C in this window to stop it.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
