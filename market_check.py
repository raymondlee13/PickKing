"""Which player-prop markets does PropLine actually carry, and does the app use them?

PropLine only returns game lines unless you name the markets you want, so this
asks for a long list of likely market names (the-odds-api naming, which
PropLine follows) and reports, per market: how many books carry it, whether
PrizePicks posts it, whether the books price it two-sided (needed to grade it),
and whether it's already in scoring.MARKETS_BY_SPORT.

Run: python market_check.py   (about 2 PropLine requests per sport)
"""

from collections import defaultdict

from config import load_config, propline_key
from propline_api import api_get, list_upcoming_events
from scoring import CONSENSUS_BOOKS, MARKETS_BY_SPORT

GAMES_PER_SPORT = 2
CANDIDATES = {
    "basketball": [
        "player_points", "player_rebounds", "player_assists", "player_threes", "player_blocks", "player_steals",
        "player_blocks_steals", "player_turnovers", "player_points_rebounds_assists", "player_points_rebounds",
        "player_points_assists", "player_rebounds_assists", "player_field_goals", "player_frees_made",
        "player_frees_attempts", "player_threes_attempts", "player_double_double", "player_triple_double",
        "player_first_basket", "player_fantasy_points", "player_offensive_rebounds", "player_defensive_rebounds",
    ],
    "americanfootball_nfl": [
        "player_pass_yds", "player_pass_tds", "player_pass_completions", "player_pass_attempts",
        "player_pass_interceptions", "player_pass_longest_completion", "player_pass_rush_yds",
        "player_pass_rush_reception_yds", "player_pass_rush_reception_tds", "player_rush_yds", "player_rush_attempts",
        "player_rush_longest", "player_rush_tds", "player_rush_reception_yds", "player_rush_reception_tds",
        "player_receptions", "player_reception_yds", "player_reception_longest", "player_reception_tds",
        "player_kicking_points", "player_field_goals", "player_pats", "player_sacks", "player_solo_tackles",
        "player_tackles_assists", "player_defensive_interceptions", "player_anytime_td", "player_1st_td",
        "player_last_td", "player_tds_over", "player_fantasy_points",
    ],
    "baseball_mlb": [
        "batter_hits", "batter_home_runs", "batter_rbis", "batter_runs_scored", "batter_hits_runs_rbis",
        "batter_total_bases", "batter_singles", "batter_doubles", "batter_triples", "batter_walks",
        "batter_strikeouts", "batter_stolen_bases", "batter_first_home_run", "batter_fantasy_score",
        "pitcher_strikeouts", "pitcher_hits_allowed", "pitcher_walks", "pitcher_earned_runs", "pitcher_outs",
        "pitcher_record_a_win", "pitcher_fantasy_score",
    ],
}


def main():
    api_key = propline_key(load_config())
    for sport, in_app in MARKETS_BY_SPORT.items():
        candidates = CANDIDATES["basketball" if sport.startswith("basketball") else sport]
        books, two_sided = defaultdict(set), defaultdict(int)
        try:
            games = list_upcoming_events(sport, api_key)[:GAMES_PER_SPORT]
        except Exception as e:
            print(f"\n{sport}: couldn't list games ({type(e).__name__})")
            continue
        for g in games:
            try:
                event = api_get(f"/sports/{sport}/events/{g['id']}/odds", api_key, {"markets": ",".join(candidates)})
            except Exception as e:
                print(f"  {g['away_team']} @ {g['home_team']}: fetch failed ({type(e).__name__})")
                continue
            for b in event.get("bookmakers", []):
                for m in b.get("markets", []):
                    books[m["key"]].add(b["key"])
                    names = {o.get("name") for o in m.get("outcomes", [])}
                    if b["key"] in CONSENSUS_BOOKS and {"Over", "Under"} <= names:
                        two_sided[m["key"]] += 1

        print(f"\n{sport} ({len(games)} game(s))")
        print(f"  {'market':36} {'books':>5}  {'PrizePicks':10} {'gradeable':10} app")
        for market in sorted(books, key=lambda m: (m not in in_app, -len(books[m]))):
            pp = "yes" if "prizepicks" in books[market] else "-"
            gradeable = "yes" if two_sided[market] else "ladder/no"
            status = "in app" if market in in_app else ("ADD?" if pp == "yes" else "not in app")
            print(f"  {market:36} {len(books[market]):5}  {pp:10} {gradeable:10} {status}")
        absent = [m for m in in_app if m not in books]
        if absent:
            print(f"  in app but not returned for these games: {', '.join(absent)}")


if __name__ == "__main__":
    main()
