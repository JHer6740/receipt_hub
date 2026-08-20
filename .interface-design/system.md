# Receipts Hub interface system

## Direction

Receipts Hub is a warm household ledger, not a generic blue finance dashboard. It should feel like well-kept receipt paper, pantry labels, and a calm notebook: useful first, quietly distinctive, and evidence-led.

The signature element is the price verdict. It pairs a concrete saving with provenance, freshness, pack basis, and the real trip/time trade-off. A cheapest-price badge without that context is incomplete.

## Palette

- Default: Sage light.
- Alternate colorways: Clay and Olive.
- Every colorway supports light and dark mode.
- Background is the page; surface is the receipt sheet; overlays use the same surface with a divider outline.
- Good is reserved for supported savings. Warning is reserved for attention or incomplete evidence. Error is destructive or failed state only.
- No gradients. Avoid decorative shadows; communicate depth through surface shifts, borders, and overlap.

## Typography

- `NotoSans` is the interface family.
- `Display` is the heading alias and uses the bundled Noto Sans files until a separate display face is supplied.
- Screen titles are 22px. Body text is 14–16px. Section labels and captions never drop below 12px.
- Prices, totals, deltas, and chart figures use tabular numerals.

## Geometry and rhythm

- 8px base rhythm; 24px screen gutter; 16px card padding.
- Card radius: 20px. Raised-sheet top radius: 28px. Field radius: 14px. Pills: fully rounded.
- Minimum tap target: 44px. Standard row and bottom-navigation height: 56px.
- Receipt edit content reserves 190px below the last field for the fixed filing footer.

## Core patterns

- `LedgerScaffold`: background page, optional compact app bar, 24px gutters, and shell navigation where permitted.
- `RaisedLedgerSheet`: lower receipt-paper surface with 28px top corners.
- `LedgerCard`: flat surface, one-pixel semantic divider, 20px radius.
- `SectionLabel`: uppercase, 12px, medium weight, 0.6px tracking.
- `MerchantMark` / `ItemMark`: short initials in a softly tinted rounded square; never rely on color alone.
- `EvidenceChip`: names `Your receipts`, `Published`, or `{N} shoppers`; freshness sits beside or below it.
- `PriceVerdict`: supported headline, exact basis, annual effect where valid, and the source line.
- `AppStatePanel`: useful loading, empty, soft-data, offline, and failure states with a next action.

## Navigation and state

- Bottom navigation appears on ledger, comparison, list, account, and receipt-view routes; it is hidden for first run, connection, capture, processing, and receipt edit.
- Collection, Rivals, and Item preserve their navigation origin for back behavior.
- Offline state is visible as `Offline · queued` and does not block local UI actions.
- Weak/outlier prices remain visible but cannot drive ranges, crowns, savings, or switching verdicts.
- All displayed prices name their source and freshness.
