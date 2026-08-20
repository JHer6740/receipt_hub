# Receipts Hub — App Description

Version 5 (multi-user) · August 2026
Prototype: `Receipts Hub v5.dc.html`
Design system: Orica Field Design System (ODS) tokens — Noto Sans, 8px spacing base, 4/8px radii, `--primary-main` #0076A6, flat surfaces, no gradients.

---

## 1. What the app is

Receipts Hub turns the paper you already collect into an argument about where you shop.

You photograph a receipt. The app reads it, files it, and remembers every line item — not just the total. Once it has seen the same item bought a few times across a few merchants, it can answer the question a receipt drawer never could: **was that a good price, and who else wanted your money for it?**

It is a personal spend ledger with a price-comparison engine sitting on top, where the comparison is grounded in what you actually bought rather than a catalogue you have to search.

It is also a **shared price index**. Each account is private, but confirmed receipts contribute anonymised prices to a pool every user draws on — so the app can quote merchants you have never walked into. Your receipts answer other people's questions, and theirs answer yours.

---

## 2. Why it exists

The premise is that **competition is the consumer's leverage, and most people never get to use it** — because they have no record of what they paid, so they cannot tell when a rival is quietly beating their usual store.

Three ideas shape the product's point of view:

**Competition benefits the buyer.** Rival merchants must earn your basket with price, range, hours and service. The app's job is to make that rivalry visible at the moment of decision, so the pressure actually reaches the merchant.

**Never compete on price alone.** A store that is only cheap is one price drop from irrelevant, and a shopper who only chases the lowest number pays in petrol, time and stock-outs. So every comparison in the app pairs price with what the merchant *wins on* — minutes away, butcher counter, bulk aisle, open till nine — and converts the gap into an hourly rate for the driving it costs you. Cheapest is a fact; better is a judgement, and the app leaves that judgement with the user.

**It is an infinite game.** There is no final score. Stores are not enemies to defeat — they are rivals who keep each other honest. The app never tells you to abandon a merchant; it tells you what each one is currently worth to you, and lets you decide when the difference matters.

The consequence for the interface: the app never shows a bare "cheapest" badge without saying what it costs to take it.

---

## 3. Who it is for

A household shopper who buys the same forty or so things on repeat across three or four merchants, spends roughly $1,100–1,300 a month, and suspects — without proof — that some of it is avoidable. They are not coupon hunters. They will change where they buy something if shown a real number, and will happily keep paying more once they know *why*.

---

## 4. The core loop

```
Capture → Read → Review → File → Aggregate → Compare → Act
```

1. **Capture** — photograph the receipt, one or several pages.
2. **Read** — five on-device stages extract merchant, date, total and lines.
3. **Review** — you confirm or correct; the app flags what it was unsure of.
4. **File** — auto-sorted into a collection; one tap to re-file.
5. **Aggregate** — collection totals, month total, six-month trend.
6. **Compare** — repurchased items gain a price history and a rival set.
7. **Act** — switch merchant, add to the list, or knowingly stay put.

Steps 1–4 are a chore the user tolerates. Steps 5–7 are the payoff. The design keeps the chore under thirty seconds so the payoff is reached often enough to compound.

---

## 5. Screens

Twelve screens, four named paths, six overlays.

### Path A — Capture to filed

| Screen | Purpose |
| --- | --- |
| **Capture** | Viewfinder with edge guides, shutter, gallery and torch. Multi-page: each shutter press adds a page to the same receipt, with a running page count. Handles camera-denied gracefully with a gallery fallback. |
| **Processing** | Five labelled stages (upload, detect, read, extract, file) with real progression. Can fail — a failed read offers *Enter manually*, which converts the failed receipt in place rather than spawning a second one. |
| **Receipt — edit mode** | Merchant, date, total, tax and line items, all editable. A balance strip reconciles line items against the stated total. Uncertain fields are flagged. Save is blocked until the receipt has a merchant and a total, and the footer names exactly which is missing. |

### Path B — Ledger

| Screen | Purpose |
| --- | --- |
| **Home** | Month total, six-month bar chart, and the basket callout into Rivals. Below: every collection with its month total and delta. Collections live here as the dashboard rather than as a separate tab. |
| **Receipts** | Every receipt on the device, newest first, with an *attention only* filter for ones that need review. Search by merchant. |
| **Receipt — view mode** | The filed receipt. Line items each carry a price verdict — "$0.30 over Coburg" or "lowest of your three stores". Toggle to edit mode from the app bar. |
| **Collection** | One collection's total, trend and receipts on a single screen — reached identically from Home, Insights or the receipt's collection chip. Empty collections offer a way out rather than a dead end. |

### Path C — Compare

| Screen | Purpose |
| --- | --- |
| **Insights** | Month total and trend across all collections, which collections are moving most, and every item you buy again with its current price and direction. The analytical view. |
| **Rivals** | The merchant-versus-merchant screen. Leads with the **spread** on your basket, ranks all three merchants on the identical basket with bars, and states what each wins on beyond price. |
| **Item** | The comparison card for a single item — the heart of the app. Detailed in §6. |
| **List** | The shopping list, quoted live at all three merchants; cheapest outlined. Items priced from your own receipts are counted so the quote's coverage is honest. |

### Path D — Account and sharing

| Screen | Purpose |
| --- | --- |
| **First run** | The explainer before anything is asked: what the app does, that prices work better pooled, exactly what is and is not shared, and the sharing switch inline. Replayable from Account. |
| **Account** | Sharing switch, contribution counts, the two plain lists of what leaves and what never leaves, then account settings. |

### Overlays
Line-item sheet · New collection · Duplicate detected · Delete confirmation · Photo zoom · Toast.

---

## 6. Where prices come from

Three sources, and the app never blurs them. Every price on screen says which one it is.

| Source | What it is | How it presents |
| --- | --- | --- |
| **Your receipts** | Prices you have personally paid | Exact figure, "bought 6 times" |
| **Crowd** | Anonymous reports from other users' confirmed receipts | "11 shoppers · seen 3 days ago · high" |
| **Published** | A chain's own listed price, collected from what it publishes | "Published · seen today" |

### Reliability
A crowd price is only as good as its agreement. Each carries the age of the newest report, how many shoppers reported it, and a confidence label:

- **High** — many reports, close together. A single figure.
- **Mixed** — enough reports, but they disagree. Shown as a **range** ($4.60–$5.00), never a false single number.
- **Thin** — too few reports to rely on. Shown dimmed, with the reason stated.
- **Outlier** — one report sits far from the rest. Flagged and discounted: "One report looks off — not counted."

### The rule that governs everything
**Weak data is displayed but never argued from.** The verdict, the could-have-saved banner, the range header and the "Best value" crown all draw from the *confirmed* pool — your own receipts, published prices, and crowd prices with real agreement behind them. A two-report price can be seen; it cannot claim a saving or wear the crown. Where rows are excluded the header says so ("across 5 confirmed prices").

Published coverage is deliberately partial — a collector will not match every line item, and pretending otherwise would be the same false confidence the app exists to remove.

---

## 7. Privacy and contribution

**Sharing is on by default, with one switch to leave**, explained before the user is asked for anything.

**Nothing is shared until a receipt is confirmed.** An unread, failed or unreviewed receipt never leaves the device — the review step is the consent gate.

**What leaves an account**
Item name, price and pack size · merchant and date · the collection it was filed under · basket total · the user's suburb.

**What never leaves**
Name and account details · card and payment details · receipt photographs · any receipt not yet confirmed.

**The crowd is a statistic, never a person.** No profiles, no contributor names, no reliability scores attached to individuals. Other users appear only as counts: "11 shoppers."

**No reciprocity gate.** Contribution is optional and unrewarded; non-contributors see the full index, freshness and confidence included. The argument for sharing is made in copy, not extracted by withholding.

**The Account screen** states contribution as three constant historical counts — receipts shared, prices contributed, prices the index gave you — and answers the question those numbers raise: turning sharing off leaves prices already contributed in the index anonymously and stops future receipts only. Counts describe the past; the switch does not rewrite it.

---

## 8. The comparison card

Reached by tapping any repurchased item. Its shape is deliberately a *results card*, not a chart.

**Could-have-saved banner.** The first thing you see is the consequence, in your own money:

> You could have kept $2.40 on this one.
> Paid $19.90 for 250 g ($79.60/kg) at Halton Fresh Market, 10 Jul. Basco Discount works out at $68.40/kg — $11.20/kg less, $72.80 a year at your rate of buying.

When you did buy at the lowest price, it flips to a calm confirmation rather than manufacturing a regret.

**Range header.** The low and high of the currently shown options, with the item mark.

**Two tabs, with counts.**
- *Where you shop* — the merchants your receipts prove you use.
- *Everywhere* — widens the set to rivals in the same category, drawn from crowd reports and published chain prices. Groceries get a discounter, a wholefoods and a convenience store plus two chains; fuel gets other fuel retailers at realistic fuel margins; coffee gets other cafés. The tab hides when a category has no alternatives, and reads "Nearby too" when no published source covers the item.

**Per pack / per unit toggle.** Because the cheapest shelf price is not always the cheapest kilo. Nearby merchants carry different pack sizes — a discounter's double pack, a convenience store's half pack — so switching basis genuinely reorders the list. Ranking, the highlighted winner and the range header all follow the chosen basis.

**Ranked rows.** Cheapest first. Each carries the merchant, its trade-off note ("22 min · limited range · double pack"), its source chip and freshness, shelf price large with unit price beneath, stock state where a source can vouch for it, and a green *save* pill measured against what you actually paid.

**The crown.** The best-value row is tinted, marked and badged. It is keyed to the verdict's winner, not to sort position — so changing the basis reorders the list without moving the crown, and a dimmed thin or outlier row can never wear it.

**Value verdict.** Below the rows, so the cheapest number never gets the last word alone — the gap restated with what taking it would cost in distance or range.

### One rule the card obeys
Both the banner and the verdict argue from exactly two numbers: **what you paid**, and **the lowest confirmed unit price in the pool currently shown**. Never the dearest-to-cheapest spread, which was never a saving available to you. Changing the sort reorders the display; it cannot change the verdict. The banner closes by naming its own provenance — "From 11 shoppers."

---

## 9. The Rivals screen

Where the product's thesis is stated plainly.

- **Spread** — the difference between the cheapest and dearest merchant on the ten items you buy again. One number for "how much is this decision worth?"
- **Same basket, three tills** — every merchant priced on the identical basket, with bars, deltas, and each one's non-price wins.
- **The verdict card** — the "never compete on price" argument in your numbers:
  > Coburg Market Co would charge $131.40 less a year. That is 19 more hours in the car — about $6.84 an hour of your time. Halton holds you with a butcher counter and late closing.
- **Where they compete hardest** — items ranked by annual money at stake, not by percentage, so attention lands where it pays.
- **Everything else you track** — the settled items, marked as such. Where all merchants charge the same, the app says so and stops arguing.
- **Two closing lines** — how many items are settled ("no price left to win on those — only hours, range and the counter") and what cherry-picking every item to its cheapest store would actually add over one trip. Usually very little, which is the point.

---

## 10. State

Eleven keys drive every render:

| Key | Meaning |
| --- | --- |
| `screen` | Which of the eleven screens is mounted |
| `editing` | Receipt screen in edit vs view mode |
| `openId` | The receipt currently open |
| `docs` / `order` | The receipt store and its display order |
| `attnOnly` | Receipts list filtered to those needing review |
| `collKey` / `collFrom` | Which collection, and where it was opened from |
| `itemIndex` / `itemFrom` | Which item, and where it was opened from |
| `cmpTab` | Comparison scope — your merchants, or everywhere |
| `cmpBasis` | Comparison basis — per pack, or per unit |
| `pages` | Pages captured into the current receipt |
| `sharing` | Whether confirmed receipts contribute to the index |
| `offline` | Connectivity, which gates sync messaging |

**Provenance keys** (`collFrom`, `itemFrom`, `rivalsFrom`) exist because the same screen is reachable from several places. Back always returns where you came from, not to a fixed parent.

---

## 11. Data model

**Receipt** — merchant, date, time, transaction number, collection, status (`review` / `confirmed` / `failed`), total, tax, page images, and line items (name, quantity, line total).

**Collection** — key, display name, month total, receipt count, delta against last month.

**Item registry** — the repurchased items. Each carries: display name, collection, purchase rhythm, times bought, purchases per year, unit size and label, a six-month price series, per-merchant prices, and recent purchase history.

**Merchant** — name, short name, minutes away, what it wins on, and a one-line character note used in the verdict copy.

**Price report** — the unit of the shared index: item, merchant, price, pack size, date, collection, suburb. Never an author. A merchant's crowd price is an aggregate of reports, carrying report count, newest date, agreement band and confidence.

**Derived at render** — unit prices, basket totals per merchant, spread, per-item price spans, annual money at stake, the cherry-pick delta, and the hourly rate of a switch. Nothing derived is stored; every figure on screen recomputes from the ledger, so no two panels can drift apart.

---

## 12. Design principles

**One number, one scope.** Every figure states what it measures. "26 receipts this month" is the collection ledger; "9 on device" is the receipt list. Two numbers that look comparable but are not is the failure mode this rule exists to prevent.

**No saving is claimed that the user could not have taken.** Comparisons are always against a real, available alternative and the real price paid.

**Units reconcile.** Where pack sizes differ, the app shows both prices and says which basis it is arguing on. Fuel talks in litres and fills; groceries in packs and kilos.

**Cheapest is never the whole verdict.** Every price advantage is paired with its cost — distance, range, hours, stock.

**Every price names its source.** A number without provenance is a rumour, and the app would rather show fewer prices than unattributed ones.

**Confidence is shown, not smoothed.** When reports disagree the app shows the range and says so, rather than averaging into a false precision.

**No instructional copy.** If a screen needs explaining, it is the wrong screen — the first-run explainer is the single exception, because consent cannot be inferred from a layout.

**Minimum type 12px, minimum hit target 44px.** Secondary text at 13px. Canvas secondary text meets 4.5:1 against the ground.

---

## 13. Version history

**v3** — Separate Detail and Review screens; Collections as its own tab; Insights split across three tabs (Spend / Items / Prices); collection picker during capture.

**v4** — Structural flattening. Detail and Review merged into one receipt screen with a mode toggle. Collections merged into Home. Each collection resolved to a single screen. Insights collapsed from three tabs to one scroll. Capture's collection picker removed in favour of auto-sorting. Quantity and unit-price columns dropped from list rows. All instructional copy removed.

**v5** — Competition made the spine. Merchant registry with per-item pricing across three merchants; the Rivals screen; the Zyft-shaped comparison card on every item; category-scoped nearby merchants; per-unit comparison with mixed pack sizes; price verdicts on filed receipt lines; live multi-merchant quote on the shopping list. Insights retained as the analytical view.

**v5 (multi-user)** — Personal accounts over a shared price index. Three provenance types on every price (your receipts, crowd, published) with freshness, report counts, agreement ranges and confidence labels; weak data shown but excluded from every claim; the crown tied to the verdict rather than the sort; an Account privacy panel with contribution counts and a single sharing switch; a first-run explainer that asks for consent before it asks for a receipt.

---

## 14. Known gaps

- Published chain prices use invented retailers, and the collection method is assumed rather than specified — a real build needs per-retailer terms, an update cadence, and a visible "as published on" stamp.
- The index is modelled, not federated: no moderation of bad reports, no handling of merchants that dispute a price, no regional partitioning beyond suburb.
- Stock state is illustrative, not live.
- No household sharing — the ledger is single-account, and the "Members" setting is not yet backed by a real multi-seat model.
- No receipt export or accounting integration.
- Distance is fixed per merchant rather than computed from the user's location at the time of the trip.
