---
version: 1
slug: "app"
primary_target: "app"
related_targets: []
---

# PickKing main app surface — Operate mode

Scope: the whole single-page app (templates/page.html, static/style.css, static/app.js) served by server.py. One visitor: Raymond, solo, local. Task: pick sport/date, browse games, scan props, tier legs, build a Power/Flex entry, log it, check results/CLV/calibration later. No accounts, no multi-tenant surface.

## Direction contract

THESIS: The tool reads like a reported ledger, not a betting-app skin — the category default here is neon/gradient sportsbook chrome (including this app's own current dark-elevated-card look), and this direction refuses it in favor of print authority: a leg is a line in a ledger, not a gamified card.

OWN-WORLD: Newspaper agate box-score typography translated to screen. Hairline column rules (1px, never radius-heavy cards), small-caps tracked section labels, a condensed slab-serif for headlines/matchups, a monospace numeral face for every stat/odds/margin value so columns of numbers align like a stat table. Near-black "wire" ground (#0d0d0c) with off-white ink (#ece7de), one spot-red masthead accent (#b3341f) for primary actions and the header rule, sparing forest-green/brick-red for hit/miss deltas. Tier grades render as a bordered "grade box" inset (like a scouting recap box), not a pill/chip. Raised with: LED-style lit state dots for live/stale data states (donated from the drum-machine challenger); strict baseline-grid discipline on the monospace numeral columns (donated from the type-specimen challenger); a value that just moved (odds/tier changed) briefly flips like a live-tile update before settling (donated from the metro-tiles challenger).

STORY: Raymond opens the ledger, picks a sport/date, scans a reported list of graded legs ranked S→C against the market bar, builds an entry from the highest-conviction lines, and later reads the calibration report as this week's "corrections" column — the tone throughout is a trusted report, never a hype push.

FIRST VIEWPORT: Masthead header (brand mark + tagline as a newspaper nameplate, thin double-rule beneath). Below it, the sport/date control bar reads as a dateline strip, not a form card. Game browser is a manifest list with hairline row dividers. The break-even reference collapses into a "reference table" callout in the same ledger typography. Primary action (scan) sits as a bold ruled button at the strip's end, not floating.

FORM: Assigned direction (candidate 4 of 7 on my own grounded list: 1 grading slab, 2 scout's clipboard, 3 market terminal, 4 press-room ledger/agate box score, 5 betting slip, 6 tote board, 7 departure board). Seed key 04a15442 (direction scope, mode operate). Weighed against catalog challengers (deep dive, sneaker boxes, drum machine, type specimen, busytown, metro tiles) on audience identification + product clarity: none won both axes against this direction; three donated disciplines listed above under OWN-WORLD.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Build path

Code-led: no image generation tool is available in this environment, so there is no comp round. Ambition is carried by this contract's FIRST VIEWPORT and the live-tile-flip signature interaction; verified in behavior at finish, not against a comp.

## Constraints preserved

- All existing functionality, endpoints, DOM ids/classes referenced by app.js's own logic, form field names server.py reads must keep working.
- Product principle: grading must read as market-derived and auditable — the ledger register reinforces this, must not be undercut by playful/gamified motion.
- Single-file simplicity: no new build tooling, no new dependencies (plain CSS + vanilla JS, matching current stack).
