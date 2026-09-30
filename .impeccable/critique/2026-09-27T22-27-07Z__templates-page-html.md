---
target: UI and site structure
total_score: 24
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:C:\\Users\\raymo\\pickking\\PickKing\\templates\\page.html"
target_fingerprint: "sha256:e1eb21ae21f2153c5fbd4f71317088bdc1189e4558c4d04fa8c91d248e8ccd42"
target_path: "C:\\Users\\raymo\\pickking\\PickKing\\templates\\page.html"
timestamp: 2026-09-27T22-27-07Z
slug: templates-page-html
---
DEGRADED: single-context (sub-agents not requested; no browser tool).

## Design Health Score: 24/40 (Acceptable)
1 Status 3 | 2 Real world 3 | 3 Control 3 | 4 Consistency 2 | 5 Error prevention 2 | 6 Recognition 2 | 7 Flexibility 2 | 8 Minimalist 2 | 9 Recovery 3 | 10 Help 2

## Specificity
Visual identity (press-room ledger) is authored and specific. Structure is category-default: three type-grouped card columns instead of a ranked table. Detector: 4x side-tab on the 5px double masthead rule -- false positive (deliberate DESIGN.md masthead rule).

## Priority Issues
- [P1] Three sticky panels stack (filter bar top:0, entry builder top:1rem, manual-pick form accidentally sticky via reused .entry-builder class, app.js:825). Fix: only filter bar sticky; builder as desktop right rail / mobile bottom slip; manual form gets own class.
- [P1] Results grouped by line type not grade (app.js:945-949). Fix: single ranked ledger table (Grade, Player, Side/Line, Type tag, Consensus, Bar, Margin); type toggles stay as filters.
- [P1] Setup (form, game list, break-even reference, clear button) stays above results. Fix: collapse to one dateline after a tab loads; move break-even numbers into the entry builder next to the multiplier.
- [P2] Home page is a dead hop duplicating view tabs. Fix: login lands on /app.
- [P2] Track view shows no numbers until clicked. Fix: auto summary (pending, hit rate by tier), one primary action, pending count in tab label.

## Persona red flags
Alex: full page reload per scan, no shortcuts, 8 alert() dialogs, raw-data debug button in main filter bar.
Casey: sticky builder covers phone viewport, goblins-first single column, 12px tab-close target, actions at top of builder.

## Minor
Manual-pick form always visible; inline style strings in app.js; explanatory prose inside working panels; Track status spans shift buttons.
