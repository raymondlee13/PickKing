"""HTML rendering: loads the page template once at import time and fills in
the per-request dynamic bits (team names, sport/entry selections, error
banners, and the JSON payload from a scan)."""

import datetime
import html
import json
import os
from string import Template

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "page.html")

with open(TEMPLATE_PATH, "r", encoding="utf-8") as _f:
    PAGE_TEMPLATE = Template(_f.read())


def render_form(team_a="", team_b="", entry="3", sport="basketball_wnba",
                 entry_type="power", error_html="", scan_payload=None):
    payload_script = ""
    if scan_payload is not None:
        payload_json = json.dumps(scan_payload).replace("</", "<\\/")
        payload_script = f'<script id="scan-payload" type="application/json">{payload_json}</script>'

    return PAGE_TEMPLATE.substitute(
        team_a=html.escape(team_a, quote=True),
        team_b=html.escape(team_b, quote=True),
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
        error_html=error_html,
        payload_script=payload_script,
    )


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
