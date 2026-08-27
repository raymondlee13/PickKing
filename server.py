"""HTTP server: routes requests to the scan/slate/log handlers and serves the
static frontend assets (templates/page.html, static/style.css, static/app.js)."""

import datetime
import json
import os
import urllib.error
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from config import load_config
from excel_logging import log_parlay_to_excel
from goblin_demon_calibration import estimate_multiplier, record_correction
from propline_api import find_event, fetch_props, list_upcoming_events, scan_slate
from scoring import (
    BASKETBALL_MARKETS, FLEX_BARS, MARKETS_BY_SPORT, POWER_PLAY_BARS,
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

    def _send_static(self, filename, content_type):
        with open(os.path.join(STATIC_DIR, filename), "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_form())
        elif parsed.path in STATIC_FILES:
            filename, content_type = STATIC_FILES[parsed.path]
            self._send_static(filename, content_type)
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
            raw_books = extract_raw_all_books(full_event)

            bar_table = POWER_PLAY_BARS if entry_type == "power" else FLEX_BARS
            bar = bar_table.get(int(entry), 55.0)
            rows, bar = build_report(full_event, bar)

            if not rows:
                error_html = '<div class="error">No gradeable legs found -- no overlapping book coverage for this game/market set.</div>'
                self._send_html(render_form(team_a, team_b, entry, sport, entry_type, error_html))
                return

            payload = rows_to_payload(rows, bar, team_a, team_b, sport, entry, entry_type, raw_books)
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
                "rawBooks": raw,
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
    print(f"PickKing running at {url}")
    print("Press Ctrl+C in this window to stop it.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
