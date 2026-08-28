# Getting OCR right the first time

**Status:** plan, not built. Written 28 August 2026 from the first real
physical-device benchmark. Nothing here has been implemented.

## The concern

> We might need some sort of way to turn the OCR data to become deterministic
> and make the user review less and get it correct the first time. Otherwise we
> risk users uninstalling the app from frustration.

That risk is real and it is measurable today. This document says what is
actually wrong, with evidence, and what to do about it in the order worth doing.

## The reframe

OCR output cannot be made deterministic. It is a model reading a creased strip
of thermal paper photographed at night. Chasing determinism *in the model* is
not the lever.

**The review burden can be made deterministic**, because a receipt carries its
own proof:

- **A stated total.** Read independently of the line items. When the lines sum
  to it, every price is corroborated by a second number that came from a
  different part of the page. That is arithmetic, not confidence.
- **Stable product codes.** `401110`, `524282`, `566385`. Once a household has
  confirmed what a code means, no future receipt needs OCR to be trusted for
  that description again.

Both are exact. Neither is a probability. That is where "deterministic" is
available, and it is enough.

## What is actually wrong

### The per-line flag carries no information

`grocery_home/ingestion.py:577`:

```python
needs_review=(
    status == ProcessingStatus.NEEDS_REVIEW
    or (item.confidence is not None and item.confidence < 0.72)
),
```

The first clause is the receipt's own status. And `extract_stored_receipt`
states the rule plainly at `ingestion.py:266`:

> Every camera/scanned input remains `needs_review` regardless of OCR
> confidence.

So for **every photographed receipt, every line is flagged, always.** The
confidence comparison after the `or` can never change the outcome. The flag is
a constant.

The interface then renders that constant as a specific claim about that
specific line — "Read with low confidence" — on all 33 rows. It is not a
low-confidence signal. It is a label that is always on, which makes it both
useless as a signal and maximally expensive to act on.

### The arithmetic that would settle it is computed and then ignored

`services.receipt_warnings` already computes `line_sum` and compares it to
`receipt.total_cents`, and the API already returns a `balance` object with
`reconciled`. The flagging never consults either.

### Evidence, from four receipts on the live service

| Receipt | Lines | Flagged | Lines sum to stated total? |
|---|---:|---:|---|
| Aldi $153.34 (21 Jul) | 33 | **33** | **yes — difference $0.00** |
| Woolworths $31.73 (23 Jul) | 10 | **10** | no — lines sum $100.48 |
| Aldi, shadowed photo | 33 | **33** | no total read at all |
| Synthetic, filed | 5 | 0 | yes |

The first row is the whole problem in one line. Thirty-three line items that
sum **to the cent** against a total read from a different part of the page, and
the app asks the person to check all thirty-three.

The second row shows the opposite failure: the lines and the total disagree by
$68.75, which almost certainly means the *total* was misread — one number, and
the one a person can check at a glance. The app instead flags ten lines and says
nothing about the total.

## The benchmark this came from

One real ALDI receipt, photographed at night, hand-held, curled, bottom third
in shadow. 720x1600, 102 KB, ~36 line items.

| Run | Result |
|---|---|
| 1 | 2.08s — duplicate (hash matched an earlier probe; dedupe working, scoped to the household) |
| 2 | 18.73s → needs_review |
| 3 | 21.65s → needs_review |

**OCR on the Pi's ARM CPU: ~19-22s end to end** — upload, detect, read, parse,
persist. The app polls a capture with a three-minute budget, so there is ample
headroom. This closes the open question from
[the Pi handover](pi-api-handover.md) §9.4.

### Accuracy on that photograph

- **Every legible price was read correctly.** Across 33 extracted lines, not one
  wrong amount.
- Merchant recognised as `Aldi`.
- Lines summed to **$168.96** against a true subtotal of **$174.35**. The
  $5.39 gap is exactly the three lines lost to shadow: $1.09 + $1.85 + $2.45.
- **Total and date: missed.** Both sit in the shadowed strip.
- It did not invent either. It warned about the missing date, the missing total,
  and the discrepancy. That behaviour is correct and must not be traded away.

A careful human reading of the same photograph recovers all of it, including the
shadowed prices, and reconciles to $174.35 exactly. So the ceiling for this
image is not where we are — the misses are recoverable, not inherent.

### A parser defect found alongside

Continuation lines are being parsed as products:

| Receipt line | Became a product row |
|---|---|
| `2.137kg Net @ 3.69 $/kg` | product, price $7.89 |
| `Qty 3 @ $9.99 ea.` | product, price $4.89 |

These are the second lines of weighed and multi-buy items. Turning them into
rows both invents products and **shifts name-to-price pairing by one row**: on
this receipt `Pper Towel DL 3pk` was given $7.46, which belongs to the
`Cut Wtrmelon Loose` beneath it. ALDI and Woolworths receipts are full of these.

## What to do, in order

### 1. Let arithmetic overrule confidence

When the line items sum to the stated total (within the existing 5c tolerance),
clear `needs_review` on every line and drop the "N line items had uncertain
text" warning.

- **Where:** `ingestion.py:577` for the write, `services.receipt_warnings` for
  the warning, and the reconciliation already in `receipt_view`'s `balance`.
- **Effect:** the Aldi $153.34 receipt goes from 33 prompts to **zero**.
- **Why it is sound:** two numbers read from different regions of the page
  agreeing to the cent is stronger evidence than any per-glyph score. If they
  agree and both are wrong, they are wrong in a way no per-line prompt would
  have caught either.
- **Effort:** small. Server-side, unit-testable, no schema change.
- **Verify:** a test that a reconciling photographed receipt has no flagged
  lines and no uncertain-text warning, and that a non-reconciling one still
  does.

### 2. When they disagree, ask about the total — not the lines

- Lines and total disagree → flag **the total**, and say so: "The lines add to
  $100.48 but the total reads $31.73." Escalate to per-line prompts only if the
  person confirms the total is right.
- Gap equals a plausible sum of missing rows (the shadow case: $5.39 =
  $1.09 + $1.85 + $2.45) → "some lines may be missing" rather than "check every
  line". Even without identifying which, "3 lines are missing" is a different
  and much smaller job than "33 lines are suspect".
- No total read at all → ask for the total only. It is the one field that
  unlocks verification of everything else.
- **Where:** `services.receipt_warnings`, plus the review screen's ordering of
  what it asks for.
- **Effort:** small-to-medium. Mostly wording and ordering, with one arithmetic
  helper.

### 3. Parse continuation lines as continuations

Recognise `^[\d.]+\s*kg Net @` and `^Qty \d+ @` (and the Woolworths
equivalents) and attach them to the preceding item as quantity, unit and unit
price instead of creating a row.

- **Removes** invented products, **fixes** the one-row name/price shift, and
  **yields real unit prices** for weighed goods — which the comparison feature
  needs anyway.
- **Where:** the line-pairing step in the OCR parser.
- **Effort:** medium. Deterministic and highly testable; the benchmark image is
  a ready-made fixture with a known answer ($174.35).

### 4. Spend the compute where it pays: the total

The stated total is the linchpin of the entire trust model — one number that
verifies thirty-three. It currently gets the same treatment as any other line,
and on this receipt it was lost.

Worth doing: locate the total/subtotal band, then re-read *just that crop* at
higher resolution with contrast normalisation, and retry before giving up. A
second pass over 5% of the page is cheap against a 19s budget, and succeeding
there is what turns 33 prompts into 0.

- **Effort:** medium. Contained in the OCR step.

### 5. Learn the product codes

These receipts carry stable codes. Once a household confirms
`401110 = Wht Soft Brd 700g`, every later receipt bearing `401110` can fill the
description with certainty and never ask again.

- **Deterministic by construction**, and it compounds: the more the app is used,
  the less there is to review. This is the real answer to "get it correct the
  first time" over the life of an account.
- **Where:** a per-household code-to-product table, written on confirm; read
  during parsing.
- **Effort:** larger. New schema, a write path at confirm time, tenancy scoping
  (per household, like everything else), and its own tests.

### 6. Catch it at capture, not after

The shadow failure was preventable before upload. If the region where the total
should be is dark, blown out or cropped, say so at the viewfinder: "the bottom
of the receipt is in shadow — retake." A retake costs five seconds; a correction
queue costs trust.

- **Effort:** medium, client-side, and it needs a rule that does not nag.

### 7. Only ask about what changes the outcome

Line-item descriptions neither block filing nor affect analytics. Merchant,
total, date and collection do. Review should ask about those and leave
descriptions alone unless the arithmetic disagrees.

## What not to do

- **Do not suppress a warning that is not corroborated.** Item 1 is safe only
  because the total is independent evidence. Hiding uncertainty without evidence
  is how the app previously showed people money that was not theirs.
- **Do not fabricate a total from the line sum.** If the total was not read, it
  was not read; the person supplies it. A total derived from the lines cannot
  then be used to verify the lines.
- **Do not silently drop lines that failed to read.** "3 lines may be missing"
  is honest; quietly filing 33 of 36 is not.

## Open questions

- Should a reconciling receipt file **automatically**, with no review step at
  all? Arithmetic says it is correct. The counter-argument is that the merchant
  and date are not covered by the sum. Suggest: auto-file when the lines
  reconcile *and* merchant and date were both read, otherwise ask only for what
  is missing.
- What tolerance? `receipt_warnings` uses 5c today. Rounding on weighed items
  can exceed that legitimately.
- Where does item 5's dictionary live if a household later disputes a mapping?
