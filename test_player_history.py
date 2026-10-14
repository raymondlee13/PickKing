"""Checks for reading ESPN box scores into PickKing's stats. No network: small
hand-made summaries in ESPN's shape. Run: python test_player_history.py"""

from player_history import _outs, name_key, parse_box_score, projection


def _summary(team_id, categories, date="2026-10-07T23:30Z"):
    return {"header": {"competitions": [{"date": date}]},
            "boxscore": {"players": [{"team": {"id": team_id}, "statistics": categories}]}}


def _athlete(name, stats, dnp=False):
    return {"athlete": {"id": name, "displayName": name}, "stats": [] if dnp else stats, "didNotPlay": dnp}


def test_basketball():
    keys = ["minutes", "points", "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "rebounds", "assists",
            "blocks", "steals", "turnovers"]
    box = parse_box_score("basketball_wnba", _summary("9", [{"keys": keys, "athletes": [
        _athlete("Breanna Stewart", ["43", "35", "2-4", "11", "6", "2", "1", "3"]),
        _athlete("Bench Player", [], dnp=True),
    ]}]))
    stats = box["players"]["Breanna Stewart"]["stats"]
    assert stats["player_points"] == 35 and stats["player_threes"] == 2 and stats["player_rebounds"] == 11
    assert stats["player_points_rebounds_assists"] == 52 and stats["player_points_rebounds"] == 46
    assert stats["player_turnovers"] == 3
    assert box["players"]["Breanna Stewart"]["team"] == "9"
    assert "Bench Player" not in box["players"]  # didn't play: no fake zeros


def test_nfl_missing_table_means_zero():
    box = parse_box_score("americanfootball_nfl", _summary("30", [
        {"name": "rushing", "keys": ["rushingAttempts", "rushingYards", "yardsPerRushAttempt", "rushingTouchdowns"],
         "athletes": [_athlete("RB One", ["20", "95", "4.8", "2"])]},
        {"name": "passing", "keys": ["completions/passingAttempts", "passingYards", "passingTouchdowns", "interceptions"],
         "athletes": [_athlete("QB One", ["19/34", "143", "0", "1"])]},
    ]))
    rb, qb = box["players"]["RB One"]["stats"], box["players"]["QB One"]["stats"]
    assert rb["player_rush_yds"] == 95 and rb["player_anytime_td"] == 2
    assert rb["player_reception_yds"] == 0  # played, no catches -> 0, not unknown
    assert qb["player_pass_completions"] == 19 and qb["player_pass_attempts"] == 34
    assert qb["player_pass_rush_reception_yds"] == 143 and qb["player_anytime_td"] == 0


def test_mlb_tables_and_outs():
    box = parse_box_score("baseball_mlb", _summary("5", [
        {"keys": ["hits-atBats", "atBats", "runs", "hits", "RBIs", "homeRuns"],
         "athletes": [_athlete("Jose Ramirez", ["2-4", "4", "1", "2", "3", "1"])]},
        {"keys": ["fullInnings.partInnings", "hits", "runs", "earnedRuns", "walks", "strikeouts"],
         "athletes": [_athlete("Some Pitcher", ["5.2", "3", "1", "1", "2", "7"])]},
    ]))
    bat, pit = box["players"]["Jose Ramirez"]["stats"], box["players"]["Some Pitcher"]["stats"]
    assert bat["batter_hits"] == 2 and bat["batter_hits_runs_rbis"] == 6 and "pitcher_strikeouts" not in bat
    assert pit["pitcher_strikeouts"] == 7 and pit["pitcher_outs"] == 17 and "batter_hits" not in pit
    assert _outs("6.0") == 18 and _outs("--") is None


def test_name_matching_and_projection():
    assert name_key("A'ja Wilson") == name_key("Aja Wilson")
    assert name_key("José Ramírez") == name_key("Jose Ramirez")
    assert name_key("Fernando Tatis Jr.") == name_key("Fernando Tatis")
    assert projection([None, None]) is None
    assert projection([10, 10, 10]) == 10
    assert projection([20, 10]) > 15  # newest game counts most


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} checks passed")
