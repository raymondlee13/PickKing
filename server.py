"""HTTP server: routes requests to the scan/slate/log handlers and serves the
static frontend assets (templates/page.html, static/style.css, static/app.js)."""

import datetime
import html
import json
import os
import urllib.error
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from config import load_config
from excel_logging import log_parlay_to_excel
from goblin_demon_calibration import estimate_multiplier, record_correction
from propline_api import fetch_props, list_upcoming_events, scan_slate, utc_to_local_date_str
from scoring import (
    BASKETBALL_MARKETS, DEFAULT_BAR, MARKETS_BY_SPORT,
    STANDARD_2PICK_LEG_MULTIPLIER, build_report, extract_raw_all_books, grade_leg,
)
from views import render_form, rows_to_payload

PORT = 8787
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Explicit allowlist of servable static files -- avoids any path-traversal
# risk from turning request paths directly into filesystem paths.
STATIC_FILES = {
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


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

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_form())
        elif parsed.path in STATIC_FILES:
            filename, content_type = STATIC_FILES[parsed.path]
            self._send_static(filename, content_type)
        elif parsed.path == "/games":
            qs = urllib.parse.parse_qs(parsed.query)
            sport = qs.get("sport", [""])[0]
            date_str = qs.get("date", [""])[0]
            if not sport:
                self._send_json({"games": []})
                return
            config = load_config()
            api_key = config.get("api_key", "")
            if not api_key or api_key == "PASTE_YOUR_PROPLINE_KEY_HERE":
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
        else:
            self._send_html("<h1>Not found</h1>", 404)

    def do_POST(self):
        if self.path == "/scan":
            self.handle_scan()
        elif self.path == "/scan_slate":
            self.handle_scan_slate()
        elif self.path == "/log_parlay":
            self.handle_log_parlay()
        elif self.path == "/calibrate":
            self.handle_calibrate()
        else:
            self._send_html("<h1>Not found</h1>", 404)

    def handle_calibrate(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
        except Exception:
            self._send_json({"success": False, "message": "Malformed request."})
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
            result.update({"bar": round(bar, 1), "margin": round(margin, 1), "tier": tier})
        self._send_json(result)

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
        event_id = form.get("event_id", [""])[0]
        team_a = form.get("team_a", [""])[0]
        team_b = form.get("team_b", [""])[0]
        sport = form.get("sport", [""])[0]

        config = load_config()
        api_key = config.get("api_key", "")

        if not api_key or api_key == "PASTE_YOUR_PROPLINE_KEY_HERE":
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

            rows, bar = build_report(full_event, DEFAULT_BAR)

            if not rows:
                error_html = '<div class="error">No gradeable legs found -- no overlapping book coverage for this game/market set.</div>'
                self._send_html(render_form(sport, error_html))
                return

            payload = rows_to_payload(rows, bar, event_id, team_a, team_b, sport, raw_books)
            self._send_html(render_form(sport, scan_payload=payload))

        except urllib.error.HTTPError as e:
            error_html = f'<div class="error">PropLine API error: {e.code} {html.escape(str(e.reason))}. Check your API key in config.json.</div>'
            self._send_html(render_form(sport, error_html))
        except Exception as e:
            error_html = f'<div class="error">Something went wrong: {html.escape(f"{type(e).__name__}: {e}")}</div>'
            self._send_html(render_form(sport, error_html))

    def handle_scan_slate(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        form = urllib.parse.parse_qs(body)
        sport = form.get("sport", [""])[0]
        slate_date = form.get("slate_date", [""])[0]

        config = load_config()
        api_key = config.get("api_key", "")

        if not api_key or api_key == "PASTE_YOUR_PROPLINE_KEY_HERE":
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
            rows, raw, scanned_games, skipped_games = scan_slate(sport, slate_date, api_key, bar, include_raw=False)

            if not scanned_games:
                error_html = f'<div class="error">No {sport.split("_")[-1].upper()} games found on {slate_date}.</div>'
                self._send_html(render_form(sport, error_html))
                return

            if not rows:
                skipped_note = f" ({len(skipped_games)} game(s) failed to fetch.)" if skipped_games else ""
                error_html = (f'<div class="error">Scanned {len(scanned_games)} game(s) but found no gradeable '
                               f'legs -- no overlapping book coverage.{skipped_note}</div>')
                self._send_html(render_form(sport, error_html))
                return

            sport_label = {"basketball_wnba": "WNBA", "basketball_nba": "NBA", "baseball_mlb": "MLB",
                           "americanfootball_nfl": "NFL"}.get(sport, sport)
            game_key = f"{sport}|slate|{slate_date}"
            label = f"{sport_label} Slate {slate_date}"
            payload = {
                "gameKey": game_key,
                "label": label,
                "bar": bar,
                "rows": rows,
                "rawBooks": raw,
                "scannedGames": scanned_games,
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


def main():
    load_config()  # creates config.json with a placeholder on first run
    server = HTTPServer(("localhost", PORT), Handler)
    url = f"http://localhost:{PORT}/"
    print(f"PickKing running at {url}")
    print("Press Ctrl+C in this window to stop it.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
