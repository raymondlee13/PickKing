---
name: PickKing
description: A press-room agate box-score ledger for grading sportsbook prop legs — a reported line, not a betting-app card.
colors:
  wire-ground: "#1a1816"
  raised-panel: "#211e1a"
  inset-well: "#131110"
  agate-ink: "#ddd6c8"
  ink-secondary: "#b8ad98"
  ink-muted: "#96896f"
  hairline-rule: "#3a352c"
  hairline-strong: "#57503f"
  masthead-accent: "#e6603a"
  masthead-accent-hover: "#ec7a58"
  accent-ink: "#17110b"
  wire-green: "#6f9a5d"
  wire-green-well: "#161c12"
  crimson-flag: "#d66080"
  crimson-well: "#1f1015"
  brass-warning: "#b3853f"
  brass-well: "#201a10"
typography:
  display:
    fontFamily: "Bevan, Georgia, 'Times New Roman', serif"
    fontSize: "1.9rem"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Bevan, Georgia, 'Times New Roman', serif"
    fontSize: "1.15rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.02em"
    fontFeature: "font-variant: small-caps"
  body:
    fontFamily: "'IBM Plex Mono', 'Consolas', 'SFMono-Regular', Menlo, monospace"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "'IBM Plex Mono', 'Consolas', 'SFMono-Regular', Menlo, monospace"
    fontSize: "0.9rem"
    fontWeight: 600
    letterSpacing: "0.05em"
    fontFeature: "font-variant: small-caps"
  subhead:
    fontFamily: "'IBM Plex Mono', 'Consolas', 'SFMono-Regular', Menlo, monospace"
    fontSize: "1rem"
    fontWeight: 600
  small:
    fontFamily: "'IBM Plex Mono', 'Consolas', 'SFMono-Regular', Menlo, monospace"
    fontSize: "0.82rem"
    fontWeight: 400
  caption:
    fontFamily: "'IBM Plex Mono', 'Consolas', 'SFMono-Regular', Menlo, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
rounded:
  none: "0px"
spacing:
  xs: "0.4rem"
  sm: "0.65rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2.5rem"
components:
  button-primary:
    backgroundColor: "{colors.masthead-accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.label}"
    padding: "0.75rem 1.4rem"
    rounded: "{rounded.none}"
  button-primary-hover:
    backgroundColor: "{colors.masthead-accent-hover}"
    textColor: "{colors.accent-ink}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
    padding: "0.5rem 0.95rem"
    rounded: "{rounded.none}"
  tier-chip-s:
    backgroundColor: "{colors.wire-green-well}"
    textColor: "{colors.wire-green}"
    rounded: "{rounded.none}"
    padding: "0.12rem 0.5rem"
  tier-chip-a:
    backgroundColor: "transparent"
    textColor: "{colors.masthead-accent}"
    rounded: "{rounded.none}"
    padding: "0.12rem 0.5rem"
---

# Design System: PickKing

## Overview

**Creative North Star: "The Press-Room Ledger"**

PickKing reads as a reported agate box score, not a betting-app dashboard. The category default it explicitly refuses is neon/gradient sportsbook chrome, including the product's own prior look (a generic dark-elevated-card dashboard with a gold accent). In its place: a near-black newsprint ground, hairline column rules, a condensed slab-serif for headlines, a monospace numeral face for every stat so figures column up like a stat table, and small-caps tracked labels standing in for section heads. A leg is a line in a ledger; grading is a stamped grade box, not a gamified chip.

This is a code-led build: no comp exists, so every value below is read directly from the shipped `static/style.css` and `templates/page.html`, not from the original direction contract's aspirations. Two disciplines named in that contract were deliberately **not** built and are not part of this system: LED-style lit/unlit state dots for "live vs. stale" data, and a brief live-tile flip on a value that "just moved." Both assumed a live-polling/streaming data model; PickKing is a one-shot scan-and-render flow with no such state to indicate, so building either would have invented an affordance for a state that doesn't exist. Do not add either to future surfaces unless the app's data model actually grows a live/stale distinction.

**Key Characteristics:**
- Near-black "wire" ground with off-white ink and exactly one spot-color accent, used for primary actions and the masthead rule only.
- Flat rectangles everywhere: no radius, no shadow, no gradient (one narrow, functional exception — see Shapes).
- Genuine small-caps (not uppercase text-transform) on every section label, tracked and tight.
- A condensed slab-serif carries headlines and matchup titles; a monospace face carries every number and every line of body text.
- Tier grade renders as a bordered inset box color-coded by tier, never a tinted card or colored pill.

## Colors

Ground is near-black with warm off-white ink; the one saturated color in the system is the masthead accent, spent sparingly on primary actions and dividers.

### Primary
- **Masthead Accent** (`#e2572e`): the system's single spot-color. Used for the masthead's double-rule, primary buttons (`button`, `.slate-btn`, `.log-parlay-btn`), active tab underline, focus rings, links, the "Regular" leg-type toggle and its A-tier grade box, and calibration badges. Re-picked mid-build from a near-identical vermillion to clear 4.5:1 contrast against `--bg`; this is the canonical value, not the pre-fix one.
- **Masthead Accent Hover** (`#ec6b45`): hover/active state for every accent-filled control.
- **Accent Ink** (`#17110b`): text color on top of the filled accent (buttons, active states) — near-black rather than white, for a printed-stamp feel rather than a glossy button.

### Neutral
- **Wire Ground** (`#131210`): page background.
- **Raised Panel** (`#1b1916`): the dateline strip (`form`), entry builder, breakeven-chart panel, sticky game-day headers — a half-step lighter than ground, never a shadowed card.
- **Inset Well** (`#0c0b0a`): recessed surfaces — text inputs, selects, raw-JSON panel, game-item hover — a half-step darker than ground.
- **Agate Ink** (`#ece6d8`): primary text and headline color.
- **Ink Secondary** (`#b3a891`): secondary reading text (browse buttons, selected-leg rows, mult-result).
- **Ink Muted** (`#8f8570`): tertiary text — labels before small-caps color, hints, footnotes, muted metadata.
- **Hairline Rule** (`#3a352c`): the standard 1px divider between rows, columns, and sections.
- **Hairline Strong** (`#57503f`): heavier structural borders — panel edges, input borders, tab-bar baseline, masthead tagline divider.

### Secondary (status accents)
- **Wire Green** (`#6f9a5d`): hit/goblin/success signal — S-tier grade box, "Goblins" toggle, over-side badges.
- **Crimson Flag** (`#d66080`): miss/demon/danger signal — "Demons" toggle, conflict badges, error panel, clear-button hover. Deliberately hue-shifted away from the accent mid-build: both started as near-identical vermillion reds and were indistinguishable when the Regular/Demons toggles sat side by side. Now a distinct rose/crimson, and both this and the accent clear 4.5:1 against `--bg`.
- **Brass Warning** (`#b3853f`): B-tier grade box, estimated-value badges, skipped-game warnings.

### Named Rules
**The One Spot-Color Rule.** The masthead accent is the only saturated color used for action and emphasis; status signal (hit/miss/caution) is carried by the separate green/crimson/brass triad, never by the accent. Don't reach for the accent to mean "success" or "danger."

**The Contrast-Is-Canonical Rule.** `--accent`, `--danger`, `--warning`, and `--text-muted` were each re-picked mid-build specifically to clear 4.5:1 contrast against `--bg`. Any future adjustment to these tokens must re-verify against that floor, not just against how the color looks.

## Typography

**Display Font:** Bevan (with Georgia, Times New Roman, serif fallback)
**Body Font:** IBM Plex Mono (with Consolas, SFMono-Regular, Menlo, monospace fallback)

**Character:** A condensed slab-serif headline face stamped over a monospace body — the pairing of a wire-service masthead and a stat-table ledger. There is no separate "UI sans"; the monospace face is the body font everywhere, so every number in the app sits in a fixed-width grid and columns align.

### Hierarchy

Six enforced steps, each bound to a CSS custom property in `static/style.css` (`--fs-xs` through `--fs-xl`) — every `font-size` in the stylesheet and in `app.js`'s inline styles references one of these tokens, no bare literals. This scale was consolidated mid-build from ~15 accidental one-off sizes (an artifact of the accessibility-floor bump pass) into a real, intentional ramp; treat any new bare `font-size: N rem` as drift to snap onto the nearest step, not a new step to add casually.

- **`--fs-xl` / Display** (1.9rem, 700, line-height 1): brand mark only (`Pick`/`King`).
- **`--fs-lg` / Headline** (1.15rem, 700, small-caps): column headers (Goblins/Regular/Demons), rendered in genuine mixed-case small-caps, not full uppercase.
- **`--fs-md` / Subhead** (1rem, 600): the break-even reference's toggle heading — the one place a label sits between body and headline weight.
- **`--fs-base` / Body & Label** (0.9rem): the monospace face at the page's base size — all reading text, stat values, raw-JSON, form labels, and leg titles (0.94rem leg-title and 0.86–0.95rem label variants all snapped to this one step).
- **`--fs-sm` / Small** (0.82rem): secondary chrome — meta text, tabs, browse buttons, badges, game-list rows, tier-chip lettering. The single most common non-base size.
- **`--fs-xs` / Caption** (0.75rem): the smallest permitted step, matching the project's hard accessibility floor of 0.75rem/12px — hint icon, badges' close kin, tab-close glyphs, footnotes.

Small-caps labels (`label`, `.stat-label`, `.brand-tagline`, `.scan-divider`, `.game-day-header`, `.column-header`, `.breakeven-chart th`) all live at `--fs-base`, one step up from where their full-caps predecessors sat, because genuine `font-variant: small-caps` renders smaller/lighter than `text-transform: uppercase` at the same size.

### Named Rules
**The Genuine Small-Caps Rule.** Section and stat labels use `font-variant: small-caps` on real mixed-case source text, never `text-transform: uppercase`. This is why the "Goblins"/"Regular"/"Demons" column-header strings ship mixed-case in `app.js` — small-caps needs real case variation to render against.

**One drift not repaired:** `.breakeven-chart h2` ("Break-even reference") still uses `text-transform: uppercase` rather than the small-caps treatment every sibling label received in this pass. It was not in scope of the finish-review's findings and is left as pre-existing drift rather than silently fixed here.

## Layout

Single centered container, `max-width: 1280px`, fluid side padding (`clamp(1rem, 4vw, 2.5rem)`). The scan controls and game browser sit in a "dateline strip" (`form`) styled with top/bottom hairline rules instead of a card border, laid directly into the page. Leg results render in a 3-column grid (Goblins / Regular / Demons) that collapses to 2 columns at 900px and 1 column at 640px. Spacing is tight and table-like: row padding around 0.65–0.85rem, section gaps around 1–1.75rem; there is no loose card-grid gutter anywhere in the system.

## Elevation & Depth

Flat by design: no `box-shadow` anywhere in the stylesheet, and every element is force-flattened to zero radius (`* { border-radius: 0 !important; }`). Depth is conveyed entirely through three tonal steps (inset well darker than ground, ground, raised panel lighter than ground) and hairline/heavy rule weight, never through shadow or lift. The one visual exception is functional, not decorative: the loading `.spinner` overrides the global flattening with `border-radius: 50% !important` because a spinning ring has to be a circle.

### Named Rules
**The No-Shadow Rule.** Nothing in this system casts a shadow or uses a gradient. A printed report doesn't have those; depth comes from the raised/inset tonal pair and rule weight only.

## Shapes

Everything is a flat rectangle: `border-radius: 0` is enforced globally with `!important`, overridden only for the spinner's circle. Borders are hairline (1px, `--rule`/`--border`) for ordinary dividers, heavier (1px `--border-strong`, or 2–3px, or a `5px double`) for structural rules — the masthead's double-rule under the nameplate and the 3px double rule under each results column header are the system's two deliberate "heavy rule" moments, both a direct newspaper-masthead convention rather than a generic accent stripe. Dashed borders mean "below threshold" or "unknown" state (tier chips); dotted borders mean "no data."

## Components

### Buttons
- **Shape:** flat rectangle, no radius, 1px solid border.
- **Primary:** filled accent (`background: #e2572e`, `color: #17110b`, 1px border same as background), `0.75rem 1.4rem` padding, uppercase label lettering, `font-weight: 600`. This is the base `button` style; `.slate-btn` and `.log-parlay-btn` inherit it directly rather than carrying their own background/border — the primary "Scan whole slate" action reads with the same weight as any other primary action, not as an outlined secondary control.
- **Hover / Focus:** background shifts to `--accent-hover` (#ec6b45) on hover; `:active` nudges 1px down. Focus uses a 2px accent outline with 2px offset, not a glow.
- **Secondary / Ghost:** `.browse-btn`, `.clear-btn`, `.type-toggle`, `.raw-toggle-btn` — transparent background, `--border-strong` or `--border` outline, muted text; hover fills to the inset well and brightens text/border toward accent (or danger, for the destructive clear button).

### Chips (Tier Grade Box)
This is the system's signature component: tier renders as a bordered inset stamp, deliberately not a colored pill or filled chip.
- **Style:** transparent or filled-well background, 1px border, small-caps-weight display-face lettering, `0.12rem 0.5rem` padding, centered.
- **State:** S-tier — filled well + green border/text. A-tier — accent border/text, no fill. B-tier — warning border/text. C-tier — neutral border, secondary text. Below-threshold / unknown — dashed border. No-data — dotted border, reduced opacity.

### Cards / Containers
There are no elevated "cards" in this system. Panels (`form`, `.entry-builder`, `.breakeven-chart`, `.raw-data-panel`) are flat rectangles on the raised-panel tone, bounded by 1px `--border-strong`, with the entry builder adding a single 2px accent top-rule to mark it as the active working panel. Internal padding runs `0.9rem–1.5rem`.

### Inputs / Fields
- **Style:** inset-well background, 1px `--border-strong` border, no radius, monospace text.
- **Focus:** border shifts to accent color; no glow or shadow.
- **Hover:** border lightens to `--text-muted`.

### Navigation
Tabs (`.tabs-bar` / `.tab`) sit on a `--border-strong` baseline; the active tab is marked by a 2px accent underline and full-ink text color, inactive tabs are muted text with no underline — a newspaper section-tab feel, not a pill nav.

Top-level view navigation (`.view-nav` / `.view-tab`, added when login/Scan-Track split shipped) reuses the exact same underline convention at larger scale, directly under the masthead double-rule: small-caps mono labels, 3px accent underline on the active view. One nav pattern for both scopes (page-level views and in-page result tabs) rather than inventing a second one.

Masthead utility links (`.masthead-links`, "Home" / "Log out") are plain muted-text links pushed to the row's far end with `margin-left: auto` — no button chrome, no icons, underline-on-hover only. They're wayfinding, not actions, and shouldn't compete visually with the brand mark or the view nav beneath it.

### Auth Pages (Login / Register) and Home
No new visual vocabulary: the login/register forms are the existing `form`/`label`/`input`/`button`/`.error` styling, just centered in a narrower `.auth-container` (max-width 420px) instead of living in the dateline strip's flex row. The post-login Home page (`.home-container`, `.home-links`, `.home-link`) is the same flat-rectangle-with-hairline-rule language as the results list: each destination is a full-width row with a top/bottom `--border` rule, `strong` heading in the body mono face (not Bevan — reserved for the masthead only), `.meta` description beneath, background lightens to `--bg-raised` on hover. Treat a new destination added to Home the same way: one more `.home-link` row, never a card grid.

### Wire-Service Badges
Distinctive custom component: `.badge` draws its own bracket glyphs via `::before`/`::after` (`content: '['` / `']'`) around plain label text, rather than using an icon font or emoji. Color alone (warning/accent/muted/danger/green) carries meaning: `[EST +2pt]`, `[CALIB]`, `[CONFLICT]`, etc.

## Do's and Don'ts

### Do:
- **Do** keep every number in the monospace face (`--font`) so stat/odds columns stay aligned; never substitute a proportional face for a value column.
- **Do** use genuine `font-variant: small-caps` on real mixed-case text for section/stat labels — not `text-transform: uppercase`.
- **Do** render tier as a bordered grade-box keyed to the status triad (wire-green / accent / brass-warning / neutral), never as a filled colored pill or a tinted row background.
- **Do** keep the masthead's `5px double` accent rule and the results columns' `3px double` header rule as the system's only two "heavy rule" moments — they read as a print convention specifically because they're rare.

### Don't:
- **Don't** use emoji, icon fonts, or glyph icon sets anywhere in this system — the sport `<select>` previously carried 🏀/⚾/🏈 and they were removed as a craft-floor violation; badges draw their own CSS-generated brackets instead.
- **Don't** add radius, shadow, or gradient to any surface — the one permitted exception is the circular loading spinner, and it exists only because a spinner must be round.
- **Don't** invent a live/stale state indicator (lit/unlit dots) or a "value just changed" flip animation for this app. Both were raised in the original direction contract and intentionally not built: PickKing's render is a one-shot scan/re-render, not a live data stream, and there is no real state for either affordance to represent.
- **Don't** give a secondary/outlined treatment to a primary call-to-action button; primary actions always inherit the base filled-accent `button` style.
