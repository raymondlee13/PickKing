---
name: PickKing
description: A prop-edge board styled like a game broadcast's score graphics.
colors:
  field-navy: "#0a1330"
  surface-navy: "#101c42"
  surface-navy-raised: "#17275a"
  surface-navy-hover: "#15245a"
  picked-navy: "#1b2a63"
  column-head-navy: "#0d1838"
  rule-navy: "#22346b"
  rule-navy-strong: "#34498a"
  text-white: "#ffffff"
  text-steel: "#c9d3f0"
  text-muted: "#93a0c8"
  broadcast-red: "#d8232a"
  bar-ink: "#ffe2e2"
  bar-shade: "rgba(0, 0, 0, 0.25)"
  score-gold: "#ffc629"
  score-gold-hover: "#ffd45c"
  pos-green: "#3ee07f"
  neg-red: "#ff5a55"
  info-blue: "#6fb4ff"
typography:
  wordmark:
    fontFamily: "'Big Shoulders Display', 'Barlow', sans-serif"
    fontSize: "2rem"
    fontWeight: 900
    lineHeight: 1
    letterSpacing: "0.01em"
  display-figure:
    fontFamily: "'Big Shoulders Display', 'Barlow', sans-serif"
    fontSize: "1.9rem"
    fontWeight: 900
    letterSpacing: "-0.01em"
    fontFeature: "tnum"
  grade:
    fontFamily: "'Big Shoulders Display', 'Barlow', sans-serif"
    fontSize: "1.5rem"
    fontWeight: 900
  headline:
    fontFamily: "'Big Shoulders Display', 'Barlow', sans-serif"
    fontSize: "1.45rem"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "0.01em"
  title:
    fontFamily: "'Big Shoulders Display', 'Barlow', sans-serif"
    fontSize: "1.5rem"
    fontWeight: 900
  label-display:
    fontFamily: "'Big Shoulders Display', 'Barlow', sans-serif"
    fontSize: "0.95rem"
    fontWeight: 700
    letterSpacing: "0.06em"
  body:
    fontFamily: "'Barlow', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: "'Barlow', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "'Barlow', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "0.78rem"
    fontWeight: 700
  mono-debug:
    fontFamily: "ui-monospace, Consolas, monospace"
    fontSize: "0.78rem"
rounded:
  sm: "2px"
  md: "2px"
  lg: "3px"
  pill: "2px"
spacing:
  xs: "0.4rem"
  sm: "0.6rem"
  md: "0.9rem"
  lg: "1.1rem"
  xl: "1.25rem"
components:
  button-primary:
    backgroundColor: "{colors.score-gold}"
    textColor: "{colors.field-navy}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0.65rem 1.2rem"
  button-primary-hover:
    backgroundColor: "{colors.score-gold-hover}"
    textColor: "{colors.field-navy}"
  button-log-entry:
    backgroundColor: "{colors.score-gold}"
    textColor: "{colors.field-navy}"
    rounded: "{rounded.md}"
    padding: "0.8rem 1.2rem"
    width: "100%"
  button-secondary:
    backgroundColor: "{colors.surface-navy}"
    textColor: "{colors.text-white}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 0.9rem"
  button-secondary-hover:
    backgroundColor: "{colors.surface-navy-hover}"
  input:
    backgroundColor: "{colors.surface-navy}"
    textColor: "{colors.text-white}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0.6rem 0.8rem"
  header-bar:
    backgroundColor: "{colors.broadcast-red}"
    textColor: "{colors.text-white}"
    height: "4rem"
  view-tab:
    textColor: "{colors.bar-ink}"
    rounded: "{rounded.pill}"
    padding: "0.45rem 1rem"
  view-tab-active:
    backgroundColor: "{colors.score-gold}"
    textColor: "{colors.field-navy}"
  grade-tag-s:
    backgroundColor: "{colors.pos-green}"
    textColor: "{colors.field-navy}"
    typography: "{typography.grade}"
    rounded: "{rounded.md}"
    size: "2.4rem"
  grade-tag-a:
    backgroundColor: "{colors.score-gold}"
    textColor: "{colors.field-navy}"
    typography: "{typography.grade}"
    rounded: "{rounded.md}"
    size: "2.4rem"
  grade-tag-b:
    backgroundColor: "{colors.info-blue}"
    textColor: "{colors.field-navy}"
    typography: "{typography.grade}"
    rounded: "{rounded.md}"
    size: "2.4rem"
  board-row:
    backgroundColor: "{colors.surface-navy}"
    padding: "0.75rem 1rem"
  board-row-hover:
    backgroundColor: "{colors.surface-navy-hover}"
  board-row-picked:
    backgroundColor: "{colors.picked-navy}"
  board-column-head:
    backgroundColor: "{colors.column-head-navy}"
    textColor: "{colors.score-gold}"
    typography: "{typography.label-display}"
    padding: "0.6rem 1rem"
  ticket-head:
    backgroundColor: "{colors.broadcast-red}"
    textColor: "{colors.text-white}"
    typography: "{typography.title}"
    padding: "0.9rem 1.1rem"
  ticket-body:
    backgroundColor: "{colors.surface-navy}"
    rounded: "{rounded.lg}"
    padding: "0.9rem 1.1rem 1.1rem"
    width: "360px"
  ticket-count:
    backgroundColor: "{colors.score-gold}"
    textColor: "{colors.field-navy}"
    rounded: "{rounded.pill}"
    height: "1.6rem"
  badge:
    backgroundColor: "{colors.surface-navy-raised}"
    textColor: "{colors.text-steel}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.45rem"
---

# Design System: PickKing

## Overview

**Creative North Star: "The Score Bug"**

PickKing's board reads like a game broadcast's on-screen graphics. A deep navy field sits under a red header bar ruled in gold. Names and lines are set in big condensed uppercase type, and grades are slanted tags like the score bugs in a broadcast corner. The personality lives in type and color, not in costume: no LED boards, no betting-slip receipts, and none of the rounded-pastel app defaults. Everything stays legible across dozens of rows.

The system is dark only. It has no light theme and the stylesheet declares `color-scheme: dark`. The rows are dense, and each one reads left to right like a stat graphic: grade tag, big name, big line, then the margin on a shared axis. Gold is the only color that asks for action. Red frames the broadcast chrome. Green and red carry meaning only where the data is directional.

**Key Characteristics:**
- Navy field and navy surfaces, with a red bar and gold rules as the chrome.
- Big Shoulders Display, 800 to 900 weight and uppercase, for everything the eye scans. Barlow for everything it reads.
- Slanted score-bug tags (skewX -10deg) for grades and the entry count.
- Near-square corners (2 to 3px) everywhere.
- Gold is the one action color: picks, commits, the active view key.

## Colors

The palette is a broadcast trio of navy, red and gold, plus a strictly semantic green, red and blue.

### Primary
- **Score Gold** (score-gold): The single action color. Used for primary buttons, the checked pick box, the active view key, the ticket count, focus outlines, text selection, links, and the rules under the header bar and on top of the entry card. Its hover state is **Score Gold Hover** (score-gold-hover). Its tint (`--accent-bg`, gold at 14%) backs secondary gold labels such as estimate and calibration badges, the "Regular" toggle and the New Scan action.

### Secondary
- **Broadcast Red** (broadcast-red): The chrome color. It fills the header bar, the entry card's head and the slanted sport tag, and it rules the top of the board (4px). It is never an action or a data signal. Text sitting on the bar that is not primary uses **Bar Ink** (bar-ink), a pale pink.

### Tertiary (semantic only)
- **Signal Green** (pos-green): More, goblin, positive margin, the S grade fill, and the "ok" states in the entry math. It has a 14% tint for toggles and type tags.
- **Signal Red** (neg-red): Less, demon, negative margin, errors, conflicts and the remove hover. It has a 16% tint. It is a separate token from Broadcast Red and the two must not be swapped.
- **Tier Blue** (info-blue): Fills the B grade tag. It has a 14% tint.

### Neutral
- **Field Navy** (field-navy): The page background. It is also the ink on every gold, green or blue fill (`--on-accent`).
- **Surface Navy** (surface-navy): The board, the entry card, the setup strip, inputs and auth forms.
- **Raised Navy** (surface-navy-raised): Rows inside the ticket, the need-line box, neutral badges, the axis track and neutral grade tags.
- **Hover Navy** (surface-navy-hover): Row and secondary-button hover.
- **Picked Navy** (picked-navy): The lifted background of a picked board row.
- **Column-Head Navy** (column-head-navy): The strip behind the board's gold column heads.
- **Rule Navy** / **Strong Rule Navy** (rule-navy, rule-navy-strong): Hairline dividers, and then input borders, the unchecked pick box and the scrollbar.
- **White** (text-white), **Steel** (text-steel), **Muted Steel** (text-muted): Primary, secondary and tertiary text.
- **Scrim** (`rgba(0,0,0,0.5)`): Dims the page behind the open bottom sheet.

### Named Rules
**The One Gold Rule.** Gold means "act here": pick, commit, or the current view. A new action gets gold. A decoration never does.

**The Earned Color Rule.** Green and red appear only for More/Less, goblin/demon, margin and pass/fail math, and blue appears only for Tier B. A status that has no direction stays in steel or neutral navy.

**The Red Is Chrome Rule.** Broadcast Red frames the page (the bar, the ticket head, the board's top rule and the sport tag). It never marks a data value. Data negatives use Signal Red.

## Typography

**Display Font:** Big Shoulders Display, 700/800/900 (with Barlow, sans-serif)
**Body Font:** Barlow, 400/500/600/700 (with system-ui, -apple-system, Segoe UI, sans-serif)
**Mono Font:** ui-monospace, Consolas, monospace (the raw-JSON debug panel only)

**Character:** A tall condensed broadcast face shouts the names and numbers, and a calm grotesque carries every sentence. Both load from Google Fonts in all four templates.

### Hierarchy
- **Wordmark** (Big Shoulders Display 900 italic, 2rem, uppercase): "PICKKING", with KING in gold, on the red bar.
- **Display figure** (Big Shoulders Display 900, 1.9rem, tabular numerals): the prop line. It is the loudest element in the row. The More/Less word in front of it is a small uppercase Barlow label in green or red.
- **Grade** (Big Shoulders Display 900, 1.5rem): the letter inside the slanted tag.
- **Headline** (Big Shoulders Display 800, 1.45rem, line-height 1.05, uppercase): player names on the board.
- **Title** (Big Shoulders Display 800 to 900, 1.35 to 1.5rem, uppercase): the game strip's matchup (800), and TICKET at 900 italic.
- **Display label** (Big Shoulders Display 700 to 800, 0.95 to 1rem, uppercase, 0.06em tracking): the gold column heads and the Scan/Track view keys. The log button uses the same face at 900, 1.3rem.
- **Body** (Barlow 400, 1rem, line-height 1.5): everything else. The secondary size is 0.875rem and the text runs to a maximum of 72ch.
- **Label** (Barlow 700, 0.78rem): badges, tags and Details toggles. Badges are sentence case, for example "Assumed 1.4x" and "Single book".

### Named Rules
**The Scan/Read Split Rule.** Display type is reserved for what the eye scans across rows: marks, names, lines, grades and heads. Anything a person reads as a sentence or a control label stays in Barlow.

**The Loud Line Rule.** In a board row, the line figure is the largest type. The player name comes second. Everything else steps down to Barlow.

## Layout

The page uses a centered container (max 1360px, with side padding `clamp(0.75rem, 3vw, 2rem)`). The Scan view has two columns: the board (fluid) and the entry card (360px) with a 1.25rem gap. Board rows share one 7-column grid across the column heads and rows (grade, leg, line, type, cons., bar, margin), so every figure aligns vertically. The margin column draws a single shared axis. Its tick is the break-even bar.

The filter bar is the only sticky element in the board column. The entry card is sticky within its own column (top 1rem, at most the viewport height minus 2rem, scrolling internally).

At 1024px and below, the layout collapses to one column and the entry card becomes a fixed bottom sheet. At 720px and below, the column heads hide and each row reflows into two lines ("grade / who" over "line / type / margin"). The cons. and bar columns drop out, and the view keys go full width under the wordmark. The setup form stacks at 640px.

The spacing rhythm is 0.4 / 0.6 / 0.9 / 1.1 / 1.25rem. Rows are padded 0.75rem by 1rem.

## Elevation & Depth

The system is mostly flat, with tonal layering. Depth comes from navy steps (field, surface, raised, picked) and from colored rules, not from shadows. Only floating surfaces get a shadow.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 1px 2px rgba(0,0,0,0.4), 0 8px 24px rgba(0,0,0,0.35)`): used on the entry card and the auth form card.
- **Picked rule** (`box-shadow: inset 0 -3px 0 #ffc629`): a gold underline inside a picked row. It is a rule, not a lift.
- **Focus ring** (`box-shadow: 0 0 0 3px` gold at 14%, with a gold border): for inputs and selects. Everything else uses a 2px gold `outline` with a 2px offset.

### Named Rules
**The Rules Not Shadows Rule.** Hierarchy is marked with 4px color rules: gold under the header bar, red on top of the board, gold on top of the entry card. Only the floating card casts a shadow.

## Shapes

Corners are near-square: 2px for controls, tags and badges, and 3px for cards and the board. The token named "pill" is also 2px, so nothing in the system is round except the loading spinner. Slant is the signature silhouette. Grade tags are skewed -10deg, and the ticket count and the sport tag are skewed -12deg. The wordmark and TICKET are set in italic. Borders are hairline navy. The strong color rules are 4px, and the picked row's rule is 3px.

## Components

### Buttons
- **Primary:** A gold fill with navy ink, Barlow 700, 2px corners and 0.65rem by 1.2rem padding. On hover it moves to Score Gold Hover, and on press it scales to 0.98. Disabled buttons drop to 50% opacity.
- **Log entry:** The ticket's commit button. It is full-width gold, set in Big Shoulders Display 900 at 1.3rem, uppercase ("LOG THIS ENTRY").
- **Secondary:** A navy surface with a strong-rule border and white Barlow text. On hover it moves to Hover Navy with a muted border.
- **Text buttons** (Details, Raw data, Clear): transparent and muted, turning white on hover.

### Grade Tags (signature)
Grade tags are 2.4rem squares skewed -10deg, with the grade letter in Big Shoulders Display 900. S is filled green, A gold and B blue, all with navy ink. C and the below/no-data states sit on Raised Navy in steel or muted text.

### Header Bar
The header bar is a Broadcast Red band (min-height 4rem) with a 4px gold bottom rule. It holds the italic wordmark. The Scan/Track view keys sit in a 25% black well: inactive keys are Bar Ink and the active key is filled gold. The Home and Log out links are Bar Ink.

### Game Strip
The game strip is a Surface Navy bar. It shows a red, italic, slanted sport tag and the matchup in display caps, then the date in Barlow muted. A gold-tint "New Scan" action sits at the far end. It expands into the setup form.

### Board
The board is a Surface Navy block with a 4px red top rule. Gold display column heads sit on Column-Head Navy. Rows are divided by hairlines and turn Hover Navy on hover. A **picked row** shows Picked Navy with the 3px gold inset bottom rule.
- **Pick check:** A 1.25rem square with 2px corners and a 2px strong-rule border that turns gold on hover. When checked it is filled gold with an authored navy SVG tick.
- **Type tag:** A single letter (R/G/D) on a tint: green for goblin, red for demon, neutral for regular, gold for discount.
- **Details:** Spread and Books appear as label/value pairs, with the label in muted Barlow 600 and the value in white. Sportsbook keys are rendered through display names (DraftKings, FanDuel, BetMGM).

### Badges
Badges are small sentence-case Barlow 700 labels on a tint, with 2px corners. Gold marks estimates and calibration (with an underlined "Fix" link), red marks conflicts, and neutral marks single-book and discount.

### Inputs / Fields
- **Style:** Surface Navy, a 1px strong-rule border, 2px corners, Barlow at 1rem and a gold caret.
- **Focus:** A gold border plus a 3px gold-tint ring.
- **Select:** The native appearance is removed and replaced with an authored SVG chevron on the right.

### Entry Card (Ticket)
The entry card is Surface Navy with a 4px gold top rule and the Float shadow. The head is Broadcast Red and carries the italic TICKET title, a slanted gold count, and a white "clears X%" summary. The count pops when a leg is added. Selected legs sit in Raised Navy rows with a Remove label that turns red on hover. The need-line box states the break-even bar in white figures with green or red verdicts.
- **At 1024px and below:** The card becomes a bottom sheet with a 36by4px grab handle and a Close/Open toggle in a 25% black well. When open, it dims the page with the scrim, and tapping the scrim closes the sheet.

### Debug Panel (deliberate exception)
The raw-data panel sets its JSON in ui-monospace at 0.78rem steel on Surface Navy. It is the only monospace in the system and it stays that way because it shows raw data.

### Motion
Motion is limited to short eased fades (120 to 160ms, `cubic-bezier(0.2, 0.8, 0.2, 1)`) on background, border and color, an 80ms press scale, and a 220ms scale pop on the ticket count (0.7, then 1.12, then 1). `prefers-reduced-motion` removes all of these, and the spinner slows down.

## Do's and Don'ts

### Do:
- **Do** use gold (score-gold) with navy ink for every commit or pick action, and for nothing decorative.
- **Do** set scanned content (names, lines, grades, heads) in Big Shoulders Display 800 to 900, uppercase, and keep sentences in Barlow.
- **Do** make the line figure the largest type in any row that shows a prop.
- **Do** slant score-bug tags (skewX -10deg for grades, -12deg for counts and sport tags) and keep corners at 2 to 3px.
- **Do** mark structure with 4px color rules (gold under red chrome, red over the board) rather than with shadows.
- **Do** use `var(--*)` tokens from `static/style.css` `:root`, since that block is the source of truth.

### Don't:
- **Don't** add a light theme or light surfaces. The system is dark only.
- **Don't** use green or red for anything but More/Less, goblin/demon, margin and pass/fail, and don't use Broadcast Red for data.
- **Don't** use metaphor costumes (LED line boards, betting-slip receipts) or generic app defaults (rounded pastel pills, violet accents). This is a PRODUCT.md brand commitment.
- **Don't** set body copy, badges or form labels in the display face. Small uppercase Barlow labels (More/Less, table heads) are fine.
- **Don't** round corners past 3px. The loading spinner is the only circle.
