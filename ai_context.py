"""Advisory-only LLM research on top of the app's own grading -- recent
performance, matchup history, injury status, and same-game correlation risk.

Deliberately NOT blended into consensus_pct/bar/margin/tier anywhere. Those
numbers come from real de-vigged sportsbook prices, which already price in
everything a search-grounded LLM might find (a book's line IS the market's
aggregate opinion, informed by exactly this kind of context). An LLM's
qualitative research is far less rigorous than that and can't produce a
calibrated probability -- treating its output as a number to fold into the
scoring pipeline would corrupt an otherwise measurable, auditable system
(see calibration_report.py, which depends on consensus_pct meaning "what the
market says," not "what an LLM guessed after reading a few articles"). So
this module only ever returns human-readable text for the user to read and
weigh themselves -- never a probability, never touches scoring.py's output.

Uses Tavily (free-tier web search, no billing account required) for the live
lookup -- current injury status, this week's performance trend -- and Groq
(free-tier hosted open model) to write the summary from those real search
results. Split this way instead of a single provider's built-in "grounding"
tool because Gemini's grounding quota turned out to be gated behind a linked
billing account even within its documented free allowance; Tavily's search
quota and Groq's generation quota are each free on their own, no card
required, and independent of each other.
"""

import json
import urllib.request
import urllib.error

from scoring import SPORT_LABELS

TAVILY_URL = "https://api.tavily.com/search"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"


class ProviderError(Exception):
    """Carries which provider failed and the raw status/detail so the
    caller can tell a Tavily search-quota problem apart from a Groq
    generation-quota problem instead of guessing from one blended error."""

    def __init__(self, provider, status, detail):
        self.provider = provider
        self.status = status
        self.detail = detail
        super().__init__(f"{provider} error {status}: {detail}")


def _post_json(provider, url, headers, payload):
    # Groq sits behind Cloudflare bot-protection that blocks urllib's default
    # "Python-urllib/x.y" User-Agent before the request ever reaches Groq's
    # own auth check (surfaces as a Cloudflare error 1010, not a real 401/403
    # from the API) -- a normal-looking User-Agent avoids that entirely.
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **headers,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except ValueError:
            detail = body
        raise ProviderError(provider, e.code, detail) from None
    except urllib.error.URLError as e:
        raise ProviderError(provider, None, str(e.reason)) from None


def _tavily_search(query, api_key, max_results=5):
    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "topic": "news",
    }
    data = _post_json("Tavily", TAVILY_URL, {"Authorization": f"Bearer {api_key}"}, payload)
    return data.get("results", [])


def _groq_complete(prompt, api_key):
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    data = _post_json("Groq", GROQ_URL, {"Authorization": f"Bearer {api_key}"}, payload)
    return data["choices"][0]["message"]["content"]


def _format_error(e):
    if isinstance(e, ProviderError):
        if e.status == 429:
            return (f"Rate limited by {e.provider}'s free tier (HTTP 429). Wait a bit and "
                     f"try again. Detail: {e.detail}")
        if e.status in (401, 403):
            return (f"{e.provider} rejected the request (HTTP {e.status}) -- check "
                     f"\"{'tavily_api_key' if e.provider == 'Tavily' else 'groq_api_key'}\" "
                     f"in config.json is correct and active. Detail: {e.detail}")
        return f"{e.provider} error {e.status}: {e.detail}"
    return f"{type(e).__name__}: {e}"


def _search_snippets(query, api_key, max_results=5):
    results = _tavily_search(query, api_key, max_results=max_results)
    if not results:
        return "No search results found."
    return "\n".join(
        f"- {r.get('title', '')} ({r.get('url', '')}): {r.get('content', '')}"
        for r in results
    )


def check_context(player, matchup, sport, market_label, side, point, tavily_key, groq_key):
    """Research one leg: recent performance, matchup history, home/away,
    injury status. Returns (success, text_or_error_message)."""
    if not tavily_key or tavily_key == "PASTE_YOUR_TAVILY_KEY_HERE":
        return False, "No Tavily API key set. Add \"tavily_api_key\" in config.json."
    if not groq_key or groq_key == "PASTE_YOUR_GROQ_KEY_HERE":
        return False, "No Groq API key set. Add \"groq_api_key\" in config.json."

    league = SPORT_LABELS.get(sport, sport)
    try:
        snippets = _search_snippets(
            f"{player} {matchup} {league} recent stats injury status news", tavily_key, max_results=6
        )
    except Exception as e:
        return False, _format_error(e)

    prompt = f"""You are helping a bettor evaluate a single player prop with real, current research -- not speculation.

Player: {player}
Matchup: {matchup}
Sport: {sport}
Market: {market_label}
The pick being evaluated: {side} {point}

Real, current search results to base your answer on:
{snippets}

Using the search results above (and saying plainly if they don't cover something), summarize:
1. Recent performance trend for this specific stat over their last several games.
2. Performance in past meetings against this specific opponent, if relevant/available.
3. Home vs. away split relevant to this game.
4. Current injury/availability status for this player, and any key teammates whose status would affect this stat (e.g. a starting QB's status affects his WRs' targets).
5. Any other notable context (weather for outdoor games, pace of play, recent depth chart changes).

Be concise -- a short paragraph per point, not an essay. If the search results don't have reliable current information for a section, say so plainly rather than guessing or relying on outdated knowledge.

End your response with exactly one line in this format, nothing after it:
LEAN: OVER
or
LEAN: UNDER
or
LEAN: NEUTRAL
based on whether this context makes hitting "{side} {point}" look more likely, less likely, or unclear relative to how it's currently priced."""

    try:
        text = _groq_complete(prompt, groq_key)
    except Exception as e:
        return False, _format_error(e)
    return True, text


def check_correlation(legs, tavily_key, groq_key):
    """legs: list of {player, matchup, market_label, side, point, sport}.
    Flags same-game/related-stat correlation risk across a built entry.
    Returns (success, text_or_error_message)."""
    if not tavily_key or tavily_key == "PASTE_YOUR_TAVILY_KEY_HERE":
        return False, "No Tavily API key set. Add \"tavily_api_key\" in config.json."
    if not groq_key or groq_key == "PASTE_YOUR_GROQ_KEY_HERE":
        return False, "No Groq API key set. Add \"groq_api_key\" in config.json."
    if len(legs) < 2:
        return False, "Select at least 2 legs to check for correlation."

    # The search query below used to be just the matchup text with no league
    # qualifier at all (e.g. "Aces @ Liberty depth chart injury report news")
    # -- a WNBA game has far less indexed coverage than an NFL one, so a
    # league-less query for a WNBA entry could and did surface NFL results
    # instead. Track which sport each matchup belongs to so the query names
    # the league explicitly.
    matchups = []
    matchup_sport = {}
    for leg in legs:
        m = leg.get("matchup", "")
        if not m:
            continue
        if m not in matchups:
            matchups.append(m)
        if m not in matchup_sport:
            matchup_sport[m] = SPORT_LABELS.get(leg.get("sport", ""), leg.get("sport", ""))

    try:
        context_blocks = []
        for m in matchups:
            query = f"{m} {matchup_sport.get(m, '')} depth chart injury report news".strip()
            context_blocks.append(f"Context for {m}:\n{_search_snippets(query, tavily_key, max_results=4)}")
    except Exception as e:
        return False, _format_error(e)

    leg_lines = "\n".join(
        f"{i + 1}. {leg.get('player', '?')} -- {leg.get('market_label', '?')} "
        f"{leg.get('side', '?')} {leg.get('point', '?')} ({leg.get('matchup', '?')})"
        for i, leg in enumerate(legs)
    )

    prompt = f"""You are checking a multi-leg parlay for correlation risk between its legs -- not calculating exact probabilities, just flagging real relationships a bettor should know about before combining these picks.

Legs in this entry:
{leg_lines}

Real, current search results for the game(s) involved:
{chr(10).join(context_blocks)}

For any legs that are in the SAME game, or involve players whose stats are likely to move together (e.g. a QB's passing yards and his top receiver's receiving yards both go up in a shootout) or move oppositely (e.g. two running backs on the same team splitting carries), call it out by leg number and explain the real relationship in one or two sentences, using the search results above for current team/depth-chart context. If legs are unrelated (different games, no meaningful stat relationship), say so plainly -- don't force a connection that isn't real.

Keep this practical and grounded, not generic speculation about "variance.\""""

    try:
        text = _groq_complete(prompt, groq_key)
    except Exception as e:
        return False, _format_error(e)
    return True, text
