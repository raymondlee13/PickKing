# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Right now: Raymond, running PickKing locally (`launch.bat`) before submitting player-prop entries on pick'em apps (PrizePicks, Underdog, Sleeper, Dabble). The job: pick a sport/date/game, scan available props, and decide which legs are real edges worth building into a Power or Flex entry.

Broader audience: the user wants this to serve other bettors eventually, but has not decided the shape (other solo users running their own instance vs. a hosted multi-user product). Login accounts exist (see Capabilities and Constraints) so the instance isn't wide open on a phone/LAN/Tailscale connection, but real multi-tenancy — per-account data isolation, a hosting story — is still undecided. Treat that part as an open product fact, not a design constraint.

## Product Purpose

Turns published sportsbook odds into a graded edge for pick'em-style prop entries, then closes the loop by tracking what was actually picked and whether the grading was right.

Success means: a leg's tier/margin reliably predicts real hit rate (see calibration_report.py), and the user trusts the numbers enough to act on them without re-deriving the math by hand each time.

## Positioning

Three things a neighboring "odds comparison" tool doesn't do:

1. De-vigs real consensus sportsbook prices (not just displaying raw odds) and grades each leg directly against the specific Power/Flex break-even bar for the entry size being built.
2. Corrects goblin/demon (alt-line) grading using a hand-verified, runtime-growable calibration table (`goblin_demon_calibration.json`) — PrizePicks doesn't expose real alt-line multipliers, so a naive tool grades goblins/demons against the wrong bar.
3. Closes the feedback loop: logs picks to a tracking workbook, checks real results and CLV, and reports whether the tiering is actually calibrated over time — instead of a one-shot recommendation nobody ever checks against outcomes.

## Operating Context

- Log in (or register), land on a home screen with two entry points: Scan & Build (the live workflow below) and Track & Calibrate (results/CLV/calibration/correlation reporting, a separate later-session task — see below).
- Single local session per run: pick sport + date, browse games, scan a single game or the whole slate.
- Legs get filtered/sorted/tiered, built into a Power or Flex entry via the entry builder, and can be logged to an Excel tracking workbook.
- After games settle: check results and CLV for logged picks, and view calibration/correlation reports to see if the grading held up.
- Optional advisory research (`ai_context.py`) surfaces recent performance, matchup history, injury status, and same-game correlation risk as human-readable text alongside a leg — read-only context, not a score.

## Capabilities and Constraints

- Local process, single shared instance: `config.json` holds API keys (PropLine, Tavily, Groq) and the tracking workbook path, shared by everyone who logs in. Login accounts exist (`auth.py`, `users.json`, gitignored) — username/password, PBKDF2-hashed, cookie sessions — but this is an access gate only, not multi-tenancy: every account sees the same scan state, the same tracking workbook, the same config. There is no per-user data isolation and no roles/admin concept; registration is open to anyone who can reach the URL (`/register`).
- Python standard library first; `openpyxl` is the one optional dependency, only needed for Excel logging. Auth uses only `hashlib`/`secrets`/stdlib `json` — no new dependency.
- Scoring (`scoring.py`) is a pure, network-free transform over real de-vigged consensus odds — this is deliberate and load-bearing for calibration to mean anything.
- The LLM research module (`ai_context.py`) is explicitly advisory-only: it must never be blended into `consensus_pct`/`bar`/`margin`/`tier`, because those numbers being purely market-derived is what makes `calibration_report.py` meaningful. Any future feature touching scoring must preserve this separation.
- Real per-user data isolation and a hosted multi-tenant shape are still undecided — see Users section. Don't build those until that's resolved; the login accounts above intentionally stop short of it.

## Evidence on Hand

- Real per-request data: live PropLine odds, a hand-verified goblin/demon multiplier table (`goblin_demon_calibration.json`), and the user's own logged pick history in their tracking workbook once populated.
- No fabricated testimonials, benchmarks, or user counts exist or should be invented — this is presently a single-user tool with no external proof points to show.

## Product Principles

1. Grading must stay market-derived and auditable — never blend qualitative or AI-sourced signals into the actual scoring numbers.
2. The feedback loop (log → check results/CLV → calibration/correlation report) is core to the product, not a bolt-on report; design should keep it visible and easy to act on each session.
3. Favor the standard library and the app's own small modules over new dependencies or services — the app installs with nothing beyond Python itself, by design.
4. Don't design ahead of the multi-user/hosting decision; keep the current single-session, single-config shape until that's explicitly resolved.
