"""HTML rendering: loads the page template once at import time and fills in
the per-request dynamic bits (sport selection, error banners, and the JSON
payload from a scan)."""

import datetime
import json
import os
from string import Template

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "page.html")

with open(TEMPLATE_PATH, "r", encoding="utf-8") as _f:
    PAGE_TEMPLATE = Template(_f.read())


def render_form(sport="", error_html="", scan_payload=None):
    payload_script = ""
    if scan_payload is not None:
        payload_json = json.dumps(scan_payload).replace("</", "<\\/")
        payload_script = f'<script id="scan-payload" type="application/json">{payload_json}</script>'

    return PAGE_TEMPLATE.substitute(
        today=datetime.date.today().isoformat(),
        sel_none="selected" if not sport else "",
        sel_wnba="selected" if sport == "basketball_wnba" else "",
        sel_nba="selected" if sport == "basketball_nba" else "",
        sel_mlb="selected" if sport == "baseball_mlb" else "",
        sel_nfl="selected" if sport == "americanfootball_nfl" else "",
        error_html=error_html,
        payload_script=payload_script,
    )


def rows_to_payload(rows, bar, event_id, team_a, team_b, sport, raw_books=None, available_markets=None):
    game_key = f"{sport}|{event_id}"
    label = f"{team_a} @ {team_b}"
    return {
        "gameKey": game_key,
        "label": label,
        "bar": bar,
        "rows": rows,
        "rawBooks": raw_books or [],
        "sport": sport,
        "gameEvents": [{"matchup": label, "eventId": event_id}],
        "availableMarkets": available_markets or [],
    }
