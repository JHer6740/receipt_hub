# Handoff: Receipts Hub — Flutter

## Overview

Receipts Hub is a mobile app that turns photographed receipts into a personal spend ledger, then uses that ledger to tell the user when another merchant is quietly charging less for the things they buy on repeat. Version 5 adds personal accounts over a **shared, anonymous price index**: confirmed receipts contribute prices that every user can draw on, so the app can quote merchants the user has never visited.

Target platform for this handoff is **Flutter** (Material 3). The app is phone-first, portrait, 390 x 844 reference viewport.

---

## About the design files

The files in this bundle are **design references created in HTML** — a working prototype showing intended look, copy and behaviour. They are **not production code to port line by line**.

Your task is to **recreate these designs as a Flutter application** using the target codebase's existing patterns (state management, routing, networking). Where this document and the HTML disagree, this document wins.

Three Dart files ARE meant to be used more or less directly, because they encode rules rather than presentation:

- `lib/theme/app_theme.dart` — every design token, ported verbatim.
- `lib/models/models.dart` — the data shapes the UI reads.
- `lib/pricing/price_comparison.dart` — the comparison engine. **Port this faithfully.** See "The rules that cannot be reinterpreted" below.

## Fidelity

**High fidelity.** Colours, type, spacing, radii, copy and interaction states are all final and specified below. Recreate them pixel-accurately using Flutter widgets — do not substitute a stock Material look. Where Flutter idiom differs from the HTML (ripples instead of hover, platform scroll physics, native back gestures), prefer the Flutter idiom.

---

## The rules that cannot be reinterpreted

The prototype went through several review rounds, and every defect found was the same category of bug: **the interface making a claim the user could not act on.** These invariants are the fix. They live in `price_comparison.dart` and must survive the port.

### 1. Weak data is displayed, never argued from
Crowd prices carry a confidence. A `thin` price (3 or fewer reports) or one flagged as an `outlier` is **shown** — dimmed, with the reason in words — but is excluded from: the verdict, the could-have-saved banner, the range header, the "Best value" crown, and any save pill.

Implemented as `PriceQuote.isConfirmed`. Every claim reads from the confirmed pool.

### 2. The verdict argues from exactly two numbers
**What the user paid**, and **the lowest confirmed unit price in the pool currently shown**. Never the dearest-to-cheapest spread — nobody was ever offered that saving.

### 3. The range header reads from the confirmed pool, in comparable units
When pack sizes differ, the header must be expressed in unit prices. A header spanning a half pack and a double pack is not a range. When rows are excluded it says so: "across 5 confirmed prices".

### 4. The crown is keyed to the verdict winner, not sort position
The tint, filled mark and "Best value" badge attach to the row identical to `best`. Changing the sort basis reorders the list; it must not move the crown.

### 5. Nothing is shared until a receipt is confirmed
The review step is the consent gate. `Receipt.mayContribute` is the only path into the index.

### 6. Historical counts do not respond to present settings
Account contribution counts describe the past. Toggling sharing off must not zero them — that would imply a retraction the product does not perform.

### 7. Every price names its source
No number appears without provenance. If you cannot say where a price came from, do not show it.

---

## Screens

Twelve screens across four paths, plus six overlays. Bottom nav (56px) shows on Home, Receipts, Collection, Insights, Rivals, Item, List, Account, and Receipt in view mode. It is hidden during Capture, Processing, Receipt edit mode and First run.

### Path A — Capture to filed

#### 1. Capture
Full-bleed dark viewfinder. Corner edge guides. Bottom bar: gallery button (left), 72px shutter (centre), torch (right). Multi-page — each shutter press increments a page counter chip shown top-centre ("Page 2"). Camera-denied state replaces the viewfinder with a message and a gallery-only affordance.

#### 2. Processing
Five labelled stages, advancing on a timer:
1. Preparing image · 2. Finding receipt sections · 3. Reading merchant and totals · 4. Checking the numbers · 5. Preparing review

Progress is a determinate bar. On failure: an error state offering **Retry** and **Enter manually**. "Enter manually" converts the failed receipt in place (keeping whatever was read) — it must NOT create a second receipt.

#### 3. Receipt — edit mode
Fields: merchant, date, time, transaction ref, total, tax, and a line-item list. Each row is name / qty / line total, tappable to open the line-item sheet. "Add line item" at the end of the list.

A **balance strip** reconciles the sum of line items against the stated total, showing the difference when they disagree. This is advisory, not blocking.

Fixed bottom footer with the save button. The scroll view needs **190px bottom padding** so the footer never covers "Add line item".

Save is blocked until `isFileable`. The button label names only what is missing — "Add a total", "Add a merchant", "Add a merchant and total" — and the blocked-tap toast uses the same phrasing.

### Path B — Ledger

#### 4. Home
- Month total as display type (38px), with delta beneath.
- Six-month bar chart, 96px tall, current month in the primary colour, others at low-alpha.
- Basket callout card into Rivals: headline + subline + chevron, 20px radius, 1px divider border.
- "Collections" section: every collection with month total and delta, tappable.

The content below the chart sits on a raised sheet — surface colour, 28px top corners only, 1px top divider.

#### 5. Receipts
Search field (merchant), an "attention only" filter chip, then receipt rows: merchant, date, collection, total, and a status marker for anything needing review. Footer states the count on device.

#### 6. Receipt — view mode
Read-only rendering with the photograph thumbnail (tap to zoom). **Line items carry a price verdict** where the item is tracked: "$0.30 over Coburg" in the warn colour, or "lowest of your three stores" in the good colour. App bar action toggles to edit mode. Overflow menu: duplicate, delete.

#### 7. Collection
One collection's total, trend and receipt list on a single screen. Reachable identically from Home, Insights and a receipt's collection chip — back returns to wherever you came from (`collFrom`).

Empty state: "Nothing filed here yet" + "Scan a receipt".

### Path C — Compare

#### 8. Insights
Month total, six-month chart, "Moving most" (collections by absolute delta), and "What you buy again" (every tracked item with current price and direction).

#### 9. Rivals
- **Spread** as the hero figure — the gap between cheapest and dearest merchant on the user's repeat basket.
- **Same basket, three tills** — each merchant with total, delta from cheapest, a proportional bar, and their non-price wins ("4 min · Closest · Butcher counter · Open till 9"). The user's usual is labelled.
- **Switch verdict card** — see `BasketComparison.switchVerdict()`. Prices the switch in hours and dollars-per-hour, and names what the incumbent holds them with.
- **Where they compete hardest** — items ranked by annual money at stake.
- **Everything else you track** — settled items ("$6.50 at all three · nothing to win") and out-of-basket items with their own spreads.
- Two closing lines: how many items are settled, and how little cherry-picking every item would add over one trip.

#### 10. Item — the comparison card
The most important screen. Top to bottom:

1. **Price history chart** — six months, with the current figure.
2. **Could-have-saved banner** — warn-tinted when the user overpaid, neutral when they did not. Headline, detail sentence, and a provenance line ("From 11 shoppers.").
3. **Results card** (1px border, 20px radius, clipped):
   - Header: 52px item mark, price range ("$4.00/L to $5.70/L"), item name, and the exclusion note if any.
   - **Scope tabs** with counts: "Where you shop N" / "Everywhere N". Label reads "Nearby too" when no published source covers the item. Tab hides entirely when the category has no alternatives.
   - **Basis toggle** (pill buttons): "Per pack" / "Per kg". Only rendered when pack sizes or units actually differ.
   - **Rows**, cheapest first by the active basis. Each: 38px merchant mark, name, trade-off note, source chip + freshness, save pill, and on the right the price with the other basis beneath and stock state where a source can vouch for it. The crowned row is tinted `actionSelected` with a filled primary mark and a "Best value" badge. Soft rows are dimmed with their reason.
4. **Value verdict card** — the gap restated with what taking it costs. Annual figure on the right.
5. **Last bought** — recent purchases.
6. **Add to list** button.

#### 11. List
Add field + button. Below it, a live quote from all three merchants as three cards, cheapest outlined in the good colour, with a coverage note ("3 of 5 priced from your receipts"). Then the to-buy list with checkboxes and delete, and a "Picked up" section.

### Path D — Account and sharing

#### 12. First run
Shown before anything is asked. App mark, headline "Your receipts, worth something to you", a paragraph on what the app does, then a bordered panel: "Prices work better pooled" explaining the index, exactly what is and is not shared, and **the sharing switch inline** (on by default). Fine print: "You can change this any time in Account. Nothing is shared until you confirm a receipt." Primary "Get started", secondary "I already have an account". Replayable from Account.

#### 13. Account
- **Sharing card** — title, note, and a 52x32 switch. Copy changes with state; the off state says future receipts stay private and full access is retained.
- **Three contribution counts** in bordered cards — receipts shared, prices contributed, prices the index gave you. **Constant regardless of the switch.** Footnote explains that prices already contributed stay in the index anonymously.
- **What leaves your account** — five checked rows.
- **What never leaves** — four lock-icon rows in secondary colour.
- **Account** settings rows, then "Replay first run" and the offline toggle.

### Overlays
Line-item sheet (bottom sheet) · New collection (dialog) · Duplicate detected (dialog) · Delete confirmation (dialog) · Photo zoom (full screen) · Toast (snackbar, 84px above the bottom when nav is visible, 24px otherwise).

---

## Interactions and behaviour

- **Motion**: 0.15–0.2s ease on background, border and elevation changes. The switch knob animates left 3px ↔ 23px. Determinate progress transitions width. No decorative animation. Honour `MediaQuery.disableAnimations`.
- **Back behaviour**: Collection, Item and Rivals are reachable from several places. Each records where it was opened from and returns there. Do not hard-code parents.
- **Blank draft discard**: backing out of a manual receipt with no merchant, no total and no line items removes it rather than leaving "Untitled receipt" in the ledger.
- **Toasts**: state the outcome ("Filed to Groceries", "Thanks — your prices help the index"). Never a bare "Saved".
- **Offline**: status line reads "Offline · queued". Nothing blocks; contributions queue.

---

## State

| Key | Meaning |
| --- | --- |
| `screen` | Current screen |
| `editing` | Receipt in edit vs view mode |
| `openId` | Receipt currently open |
| `docs` / `order` | Receipt store and display order |
| `attnOnly` | Receipts list filtered to those needing review |
| `collKey` / `collFrom` | Collection, and its provenance |
| `itemIndex` / `itemFrom` | Item, and its provenance |
| `cmpTab` | Comparison scope (your stores / everywhere) |
| `cmpBasis` | Comparison basis (per pack / per unit) |
| `pages` | Pages captured into the current receipt |
| `sharing` | Whether confirmed receipts contribute to the index |
| `offline` | Connectivity |

Nothing derived is stored. Totals, spreads, unit prices and verdicts all recompute from the ledger on read, so two panels cannot drift apart. Keep this property — it is why the numbers agree.

---

## Design tokens

All values are in `lib/theme/app_theme.dart` as an `AppColors` `ThemeExtension` plus `AppText`, `AppRadii`, `AppSpacing`. Three colourways (Sage, Clay, Olive) x light/dark. **Sage light is the default.**

### Sage light (reference)
| Role | Value |
| --- | --- |
| background | `#F5EAD8` |
| surface (raised sheet) | `#FDF8EE` |
| divider | `rgba(32,30,29,.14)` |
| text primary | `#201E1D` |
| text secondary | `#6F6455` |
| action hover | `rgba(32,30,29,.05)` |
| action selected | `rgba(32,30,29,.07)` |
| primary | `#5F6F47` |
| on primary | `#FDF8EE` |
| error | `#A8432F` |
| warn background | `#F2E2CD` |
| warn foreground | `#5C3A17` |
| input border | `rgba(32,30,29,.22)` |

### Type
Noto Sans throughout; a display face for headings (`.disp`, letter-spacing -0.01em). **Tabular figures on every price, total and delta** — `FontFeature.tabularFigures()`. The columns depend on it.

| Role | Size / weight |
| --- | --- |
| Hero figure | 38–42px display |
| Screen title | 22px display |
| Card headline | 15px |
| Body | 15–16px |
| Secondary / notes | 13px |
| Chips, captions, stock | 12px |
| Section label | 12px w500, 0.6px tracking, uppercase |
| Button | 15px w500, 0.46px tracking |

**Nothing below 12px. Tap targets never below 44px.**

### Radii
20px cards and verdict panels · 28px sheet top corners · 14px inputs · 999px pills · 11px merchant mark (38px) · 14px item mark (52px).

### Spacing
24px screen gutter · 16px card padding · 56px minimum row height · 44px minimum tap target · 190px bottom padding in receipt edit mode.

---

## Assets

No bitmap assets. Icons are Material glyphs (add, chevrons, delete, lock, check, person, search, receipt) — use `Icons.*` or Material Symbols. The app mark is a receipt glyph on a primary-filled 56px rounded square. Merchant marks are two-letter initials, not logos. Receipt photographs are user content; the prototype uses placeholders.

**Fonts**: Noto Sans (all weights used: 400, 500). Add the display face to `pubspec.yaml` as family `Display`, or substitute the codebase's existing display face.

---

## Files in this bundle

| File | What it is |
| --- | --- |
| `Receipts Hub v5.dc.html` | The interactive prototype. Open in a browser; the left rail switches screens, states and colourways. |
| `Receipts Hub - App Description.md` | Product description — intent, rationale, principles, version history. Read this for *why*. |
| `lib/theme/app_theme.dart` | Design tokens as ThemeData + ThemeExtension. |
| `lib/models/models.dart` | Data models, including the confidence and provenance types. |
| `lib/pricing/price_comparison.dart` | The comparison engine. Port faithfully. |

## Suggested build order

1. Theme and tokens; verify all three colourways against the prototype.
2. Models and the comparison engine, with unit tests for the seven invariants above.
3. Item screen — it exercises the most rules and will surface model gaps early.
4. Home, Insights, Rivals.
5. Capture, Processing, Receipt edit/view.
6. Account, First run, List.
7. Overlays and toasts.

## Open questions for the product owner

- Published chain prices use invented retailers in the prototype. Real sources need per-retailer terms, an update cadence, and an "as published on" stamp.
- The index is modelled, not federated: no moderation of bad reports, no merchant dispute path, no regional partitioning beyond suburb.
- Stock state is illustrative. Decide whether it ships or is cut until a real source exists.
- The "Members" account setting implies multi-seat households, which is not designed yet.
