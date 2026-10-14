"""Tune and test the gap adjustment (scoring.shift_over_prob / GAP_SHAPES).

Wherever two sportsbooks price the same player/stat at nearby lines, hide one
book's real no-vig price, predict it from the other book's line, and compare.
No waiting for game results -- the book's own price is the answer key.

Per market: every candidate shape/width is scored on half the games (train);
the best one is then graded on the OTHER half (test), so a width can't just
memorize the answers. A market qualifies when its test miss is within
GOOD_ENOUGH points and beats the old way (reusing the neighbor's price as-is).
Prints a GAP_SHAPES table to paste into scoring.py.

Caveat: two books often post different lines BECAUSE they disagree, so some
miss is book disagreement no shape can remove. "same-line" shows how far apart
books are when they price the SAME line -- the best any prediction can hope for.

Run: python gap_adjust_check.py   (uses live PropLine odds from config.json)
"""

from collections import defaultdict

from config import load_config, propline_key
from propline_api import api_get, fetch_props
from scoring import CONSENSUS_BOOKS, MARKETS_BY_SPORT, MAX_HOLD, american_to_prob, devig_two_way, shift_over_prob

GAMES_PER_SPORT = 10
GOOD_ENOUGH = 3.0   # test miss, in probability points, to qualify
MIN_TEST_PAIRS = 40  # rows on each half; each comparison counts twice (both directions), so ~20 real ones
# Biggest line gap tested per market (others: 1). Points and yards move in
# bigger steps than counts, so books' lines sit further apart.
MAX_GAP = {
    "player_points": 2.0, "player_points_rebounds_assists": 2.0,
    "player_pass_yds": 10.0, "player_rush_yds": 10.0, "player_reception_yds": 10.0,
    "player_pass_rush_reception_yds": 10.0,
}
CANDIDATES = (
    [("poisson", None)]
    + [("count", d) for d in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.7, 2.0, 2.5, 3.0, 4.0, 5.0, 6.5, 8.0, 10.0)]
    + [("scale", round(0.05 * i, 2)) for i in range(2, 41)]
)


def _book_lines(event):
    """{(market, player): [(book, line, no-vig over prob), ...]} -- each book
    lists one two-way line per player (alt lines come as X+ ladders instead)."""
    lines = defaultdict(list)
    for book in event.get("bookmakers", []):
        if book["key"] not in CONSENSUS_BOOKS:
            continue
        for market in book.get("markets", []):
            prices = defaultdict(dict)
            for o in market.get("outcomes", []):
                if o.get("point") is not None and o.get("description"):
                    prices[(o["description"], o["point"])][o["name"]] = o["price"]
            for (player, point), sides in prices.items():
                if "Over" in sides and "Under" in sides:
                    po, pu = american_to_prob(sides["Over"]), american_to_prob(sides["Under"])
                    if po + pu - 1 > MAX_HOLD:
                        continue  # untraded exchange quote -- skipped in grading too
                    p = devig_two_way(po, pu)
                    if p is not None and 0.02 < p < 0.98:
                        lines[(market["key"], player)].append((book["key"], point, p))
    return lines


def _collect(api_key):
    """pairs[market] = [(game_index, from_line, from_p, line, truth)], floor[market] = [same-line gaps]."""
    pairs, floor = defaultdict(list), defaultdict(list)
    game_index = 0
    for sport, markets in MARKETS_BY_SPORT.items():
        try:
            events = api_get(f"/sports/{sport}/events", api_key)[:GAMES_PER_SPORT]
        except Exception as e:
            print(f"{sport}: couldn't list games ({type(e).__name__})")
            continue
        for e in events:
            try:
                event = fetch_props(sport, e["id"], api_key, markets)
            except Exception:
                continue
            game_index += 1
            for (market, _player), quotes in _book_lines(event).items():
                for i, (book_a, line_a, pa) in enumerate(quotes):
                    for book_b, line_b, pb in quotes[i + 1:]:
                        if book_a == book_b:
                            continue
                        gap = abs(line_a - line_b)
                        if gap == 0:
                            floor[market].append(abs(pa - pb) * 100)
                        elif gap <= MAX_GAP.get(market, 1.0):
                            pairs[market].append((game_index, line_b, pb, line_a, pa))
                            pairs[market].append((game_index, line_a, pa, line_b, pb))
    return pairs, floor


def _miss(rows, shape):
    return sum(abs(shift_over_prob(fl, fp, line, shape) - truth) for _, fl, fp, line, truth in rows) * 100 / len(rows)


def main():
    pairs, floor = _collect(propline_key(load_config()))
    print(f"{'market':32} {'pairs':>6} {'same-line':>9} {'old miss':>9} {'best shape':>16} {'test miss':>10}  verdict")
    chosen = {}
    for market, rows in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        train = [r for r in rows if r[0] % 2 == 0]
        test = [r for r in rows if r[0] % 2 == 1]
        same = f"{sum(floor[market]) / len(floor[market]):7.1f}pt" if floor[market] else f"{'-':>9}"
        if len(train) < MIN_TEST_PAIRS or len(test) < MIN_TEST_PAIRS:
            print(f"{market:32} {len(rows):6} {same} {'':>9} {'':>16} {'':>10}  too few pairs")
            continue
        big_lines = any(r[1] > 30 for r in rows)  # Poisson is slow and wrong-shaped for yards
        shapes = [s for s in CANDIDATES if not (s[0] == "poisson" and big_lines)]
        best = min(shapes, key=lambda s: _miss(train, s))
        test_miss = _miss(test, best)
        old_miss = sum(abs(fp - truth) for _, _, fp, _, truth in test) * 100 / len(test)
        label = best[0] if best[1] is None else f"{best[0]} {best[1]}"
        if best in (shapes[-1], ("count", 10.0)):
            label += "*"  # best is the widest tried: widen CANDIDATES before trusting it
        if test_miss <= GOOD_ENOUGH and test_miss < old_miss:
            verdict = "QUALIFIES"
            chosen[market] = (best[0], best[1], MAX_GAP.get(market, 1.0))
        else:
            verdict = "exact match only"
        print(f"{market:32} {len(rows):6} {same} {old_miss:7.1f}pt {label:>16} {test_miss:8.1f}pt  {verdict}")

    print("\nPaste into scoring.py:\nGAP_SHAPES = {")
    for market, (shape, width, gap) in sorted(chosen.items()):
        print(f'    "{market}": ("{shape}", {width}, {gap}),')
    print("}")


if __name__ == "__main__":
    main()
