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

Uses Google's Gemini API with the Google Search grounding tool, since none
of this (current injury status, this week's performance trend) exists in
any model's training data -- it has to come from a live search.
"""

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

MODEL = "gemini-3.5-flash-lite"


def _run(api_key, prompt):
    client = genai.Client(api_key=api_key)
    interaction = client.interactions.create(
        model=MODEL,
        input=prompt,
        tools=[{"type": "google_search"}],
    )
    return interaction.output_text


def _format_error(e):
    """Gemini's SDK exceptions carry a real HTTP status_code even though
    there's no public exception-class path to import and catch by type (the
    concrete class lives under a private module) -- check the status instead
    of the class so this doesn't depend on an internal SDK path that could
    move between versions."""
    status = getattr(e, "status_code", None)
    if status == 429:
        return ("Rate limited by Gemini's free tier (HTTP 429). Search-grounded requests have "
                "their own quota separate from plain generation, and free-tier keys often start "
                "with a low per-minute limit too. Check your actual limits at "
                "https://aistudio.google.com/rate-limit, then wait a bit and try again.")
    if status == 401 or status == 403:
        return "Gemini rejected the API key (check \"gemini_api_key\" in config.json is correct and active)."
    return f"{type(e).__name__}: {e}"


def check_context(player, matchup, sport, market_label, side, point, api_key):
    """Research one leg: recent performance, matchup history, home/away,
    injury status. Returns (success, text_or_error_message)."""
    if not GENAI_AVAILABLE:
        return False, "google-genai isn't installed. Run: pip install -U google-genai"
    if not api_key or api_key == "PASTE_YOUR_GEMINI_KEY_HERE":
        return False, "No Gemini API key set. Add \"gemini_api_key\" in config.json."

    prompt = f"""You are helping a bettor evaluate a single player prop with real, current research -- not speculation.

Player: {player}
Matchup: {matchup}
Sport: {sport}
Market: {market_label}
The pick being evaluated: {side} {point}

Research and summarize using real, current information:
1. Recent performance trend for this specific stat over their last several games.
2. Performance in past meetings against this specific opponent, if relevant/available.
3. Home vs. away split relevant to this game.
4. Current injury/availability status for this player, and any key teammates whose status would affect this stat (e.g. a starting QB's status affects his WRs' targets).
5. Any other notable context (weather for outdoor games, pace of play, recent depth chart changes).

Be concise -- a short paragraph per point, not an essay. If you can't find reliable current information for a section, say so plainly rather than guessing or relying on outdated knowledge.

End your response with exactly one line in this format, nothing after it:
LEAN: OVER
or
LEAN: UNDER
or
LEAN: NEUTRAL
based on whether this context makes hitting "{side} {point}" look more likely, less likely, or unclear relative to how it's currently priced."""

    try:
        text = _run(api_key, prompt)
    except Exception as e:
        return False, _format_error(e)
    return True, text


def check_correlation(legs, api_key):
    """legs: list of {player, matchup, market_label, side, point}. Flags
    same-game/related-stat correlation risk across a built entry. Returns
    (success, text_or_error_message)."""
    if not GENAI_AVAILABLE:
        return False, "google-genai isn't installed. Run: pip install -U google-genai"
    if not api_key or api_key == "PASTE_YOUR_GEMINI_KEY_HERE":
        return False, "No Gemini API key set. Add \"gemini_api_key\" in config.json."
    if len(legs) < 2:
        return False, "Select at least 2 legs to check for correlation."

    leg_lines = "\n".join(
        f"{i + 1}. {leg.get('player', '?')} -- {leg.get('market_label', '?')} "
        f"{leg.get('side', '?')} {leg.get('point', '?')} ({leg.get('matchup', '?')})"
        for i, leg in enumerate(legs)
    )

    prompt = f"""You are checking a multi-leg parlay for correlation risk between its legs -- not calculating exact probabilities, just flagging real relationships a bettor should know about before combining these picks.

Legs in this entry:
{leg_lines}

For any legs that are in the SAME game, or involve players whose stats are likely to move together (e.g. a QB's passing yards and his top receiver's receiving yards both go up in a shootout) or move oppositely (e.g. two running backs on the same team splitting carries), call it out by leg number and explain the real relationship in one or two sentences, using current team/depth-chart context. If legs are unrelated (different games, no meaningful stat relationship), say so plainly -- don't force a connection that isn't real.

Keep this practical and grounded, not generic speculation about "variance.\""""

    try:
        text = _run(api_key, prompt)
    except Exception as e:
        return False, _format_error(e)
    return True, text
