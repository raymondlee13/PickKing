"""Hide-one-line test for the Poisson gap adjustment (scoring.shift_over_prob).

Wherever a sportsbook prices the same player/stat at two lines up to
GAP_ADJUST_MAX apart, hide its real no-vig price at one line, predict it from
the other, and compare. No waiting for game results -- the book's own price is
the answer key. Reports, per market, the average miss for the Poisson shift vs
the old way (reusing the neighbor's price unchanged). A market belongs in
scoring.GAP_ADJUST_MARKETS only if its Poisson miss is small.

Run: python gap_adjust_check.py   (uses live PropLine odds from config.json)
"""

from collections import defaultdict

from config import load_config, propline_key
from propline_api import api_get, fetch_props
from scoring import (
    CONSENSUS_BOOKS, GAP_ADJUST_MAX, MARKETS_BY_SPORT, american_to_prob, devig_two_way, shift_over_prob,
)

GAMES_PER_SPORT = 8
GOOD_ENOUGH = 3.0  # avg miss, in probability points, to qualify for GAP_ADJUST_MARKETS
MIN_PAIRS = 20     # fewer pairs than this isn't enough to judge a market


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
                    p = devig_two_way(american_to_prob(sides["Over"]), american_to_prob(sides["Under"]))
                    if p is not None and 0.02 < p < 0.98:
                        lines[(market["key"], player)].append((book["key"], point, p))
    return lines


def main():
    api_key = propline_key(load_config())
    misses = defaultdict(lambda: {"raw": [], "poisson": [], "bias": [], "floor": []})
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
            for (market, _player), quotes in _book_lines(event).items():
                for i, (book_a, line_a, pa) in enumerate(quotes):
                    for book_b, line_b, pb in quotes[i + 1:]:
                        if book_a == book_b:
                            continue
                        m = misses[market]
                        gap = abs(line_a - line_b)
                        if gap == 0:
                            m["floor"].append(abs(pa - pb) * 100)  # books disagreeing at the SAME line
                        elif gap <= GAP_ADJUST_MAX:
                            for line, truth, from_line, from_p in ((line_a, pa, line_b, pb), (line_b, pb, line_a, pa)):
                                predicted = shift_over_prob(from_line, from_p, line)
                                m["raw"].append(abs(from_p - truth) * 100)
                                m["poisson"].append(abs(predicted - truth) * 100)
                                m["bias"].append((predicted - truth) * 100)

    # "same-line" = how far two books are apart when they price the SAME line --
    # the noise floor no prediction across books can beat.
    print(f"{'market':34} {'pairs':>6} {'same-line':>10} {'old miss':>9} {'poisson miss':>13} {'bias':>6}  verdict")
    qualifying = []
    for market, m in sorted(misses.items(), key=lambda kv: -len(kv[1]["raw"])):
        n = len(m["raw"])
        floor = f"{sum(m['floor']) / len(m['floor']):8.1f}pt" if m["floor"] else f"{'-':>10}"
        if n == 0:
            print(f"{market:34} {n:6} {floor} {'-':>9} {'-':>13} {'-':>6}  no lines 1 apart")
            continue
        raw, poisson = sum(m["raw"]) / n, sum(m["poisson"]) / n
        bias = sum(m["bias"]) / n
        if n < MIN_PAIRS:
            verdict = "too few pairs"
        elif poisson <= GOOD_ENOUGH and poisson < raw:
            verdict = "QUALIFIES"
            qualifying.append(market)
        else:
            verdict = "exact match only"
        print(f"{market:34} {n:6} {floor} {raw:8.1f}pt {poisson:12.1f}pt {bias:+5.1f}  {verdict}")
    print(f"\nGAP_ADJUST_MARKETS = {set(sorted(qualifying))}")


if __name__ == "__main__":
    main()
