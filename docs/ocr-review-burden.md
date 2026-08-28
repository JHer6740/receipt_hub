# Getting OCR right the first time

**Status:** items 1-4 built and tested, 28 August 2026. Items 5-7 not built —
see [What is built](#what-is-built) at the end for exactly what shipped, what
did not, and why.

Written from the first real physical-device benchmark.

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

## The losses were in pairing, not in reading

Dumping the raw OCR lines for the benchmark photograph settled what was
recoverable. Every number the parser "missed" was in fact read, at full
confidence:

| OCR line | Text | Confidence | What the parser did |
|---|---|---:|---|
| 107 | `1.09` | 1.00 | discarded — no description beside it |
| 108 | `1.85` | 1.00 | discarded |
| 110 | `2.45` | 1.00 | discarded |
| 111 | `174.35` | 1.00 | discarded — the "Subtotal" label was lost to shadow |
| 112 | `174.35` | 1.00 | discarded — the "Total" label was lost to shadow |

Mean OCR confidence over the whole receipt: **0.984**. So this was never a
reading problem, and item 4 does not need a second pass over the image after
all — the total is already in hand and was being thrown away because
`_find_total` required the literal word "TOTAL" on the line.

That also means the "3 lines lost to shadow" were not lost. They were read and
dropped, which is a different and much more fixable thing.

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

## What is built

Implemented and tested on 28 August 2026. **The service needs a redeploy for
any of it to reach the phone.**

### Items 1-4, done

- **Arithmetic overrules confidence.** `ingestion.persist_parsed_receipt` no
  longer ORs the receipt's status into every line. A line is flagged only when
  its own text was read below `LINE_REVIEW_CONFIDENCE`, and not at all when the
  lines sum to the stated total within `RECONCILE_TOLERANCE_CENTS` — one
  constant now shared by the write path and the review path, in `models.py`.
- **Disagreement names both numbers.** `services.receipt_warnings` replaces
  "Line items differ from the receipt total by $12.81" with "The total reads
  $19.99 but the lines add to $7.18, so $12.81 of lines are missing.", and says
  "Check the total." when the lines exceed it instead.
- **Continuation lines attach instead of becoming products.** `Qty 3 @ $9.99
  ea.` survives OCR reading the `@` as a `0`, `O` or `a` and the decimal point
  as a comma; `2.021kg Net @ 3.69 $/kg` has a handler at all for the first
  time. Both hand on a product that was merged onto the same spatial row, so
  nothing is swallowed with them.
- **An unlabelled amount can serve as the total**, but only when it is at least
  the sum of the lines — a total below its own items is not a total — and a
  repeated value wins, because a receipt prints its total beside its subtotal.
- **Amounts with no description are reported, not dropped**: "4 amounts were
  read without a matching product."

### Measured against the benchmark receipt

| | Before | After |
|---|---|---|
| Total | not read | **$174.35** |
| `Pper Towel DL 3pk` | $7.46 (the row below's price) | **$4.89** |
| `Qty 3 0 $9,99 ea` | a product, $4.89 | attached: 3 @ $9.99 |
| `2.021kg Net @ 3.69 $/kg` | a product, $2.59 | attached: 2.021 kg @ $3.69 |
| Weighed items | no unit price | unit prices on all four |
| Unexplained shortfall | silent | "4 amounts were read without a matching product" |
| Lines flagged on a balancing receipt | all of them | **none** |

The $6.48 still missing from that photograph is the four amounts whose
descriptions the shadow ate. They are now named rather than quietly absent.

For the Aldi receipt uploaded from the phone — 33 lines summing to $153.34 to
the cent — this takes review from **33 prompts to none**.

Backend suite: **104 passing**, up from 94. The new tests cover the misread
at-sign, the weight continuation, a merged row handing on its product, the
total fallback and its guard, orphan amounts, the comma decimal, per-line
flagging with and without corroboration, and the reworded shortfall.

### Items 5-7, not built

- **Product-code learning (5)** is a feature, not a fix: new schema, a write
  path at confirm time, tenancy scoping and its own tests. It is the largest
  remaining lever and the only one that keeps paying off with use.
- **Capture-time shadow warning (6)** needs a rule that does not nag, and
  tuning it means holding the phone over real receipts in bad light. Worth
  doing on the next device session rather than guessed at from a desk.
- **Escalating to line prompts only after the total is confirmed (7)** is a
  client interaction. The server now says which number is in question; the
  review screen does not yet stage the questions that way.

### Still not decided

Whether a receipt whose lines reconcile, and whose merchant and date were both
read, should file with **no review step at all**. Nothing above changes that:
a photographed receipt still goes to review, it just arrives with nothing
flagged. Turning that into an automatic file is a product decision, and the
argument against it is that the arithmetic covers the money but not the
merchant or the date.
