# Privacy Policy

**Draft — not for publication until legally reviewed.**

**Effective date:** {{EFFECTIVE_DATE}}
**Last updated:** {{EFFECTIVE_DATE}}

## Who we are

Receipt Hub is operated by {{OPERATOR_LEGAL_NAME}} ("we", "us"), trading as
{{OPERATOR_TRADING_NAME}}, of {{OPERATOR_ADDRESS}}, Australia.

For anything in this policy, including a request about your information or a
complaint:

- **Privacy contact:** {{PRIVACY_EMAIL}}
- **General support:** {{SUPPORT_EMAIL}}
- **Postal:** {{OPERATOR_ADDRESS}}

This policy applies to the Receipt Hub app and to {{PUBLIC_DOMAIN}}.

## What Receipt Hub does, in one paragraph

You photograph a receipt. We read it, file it, and keep the line items so you
can see where your household's money goes and compare what you buy repeatedly.
Receipts are filed into a *household* — a shared ledger that you and the people
you approve can both see. That sharing is the point of the product, and it is
described in detail under "Who can see your receipts".

## What we collect

### Information you give us

| What | Why we have it |
|---|---|
| Email address | Identifies your account and is how you sign in |
| Password | Verifying it is you. Stored only as an argon2id hash — we cannot read your password |
| Display name | Shown to other people in your household so they know who filed what |
| Household name | Labels the shared ledger |
| Receipt photographs and PDFs | The source document you asked us to read |
| Corrections you make | Your fix is the authority when our reading was wrong |
| Shopping list items and notes | The shared list feature |

### Information we derive from your receipts

We read your receipts and store what we extract. This is the substance of what
we hold about you, so it is worth being specific. It can include:

- Merchant name and store identifier
- Purchase date and time
- Transaction and terminal references printed on the receipt
- Total, subtotal, tax and any savings
- Every line item: description, quantity, unit, unit price and line total
- A category for each line item
- A confidence score, and a flag where our reading was uncertain
- A fingerprint used to notice when the same receipt is uploaded twice

**Receipts can reveal more than shopping.** A receipt may show where you were
and when, what medication or other sensitive goods you bought, and fragments of
payment details printed by the merchant. We do not ask for that information —
it arrives because it is on the document — but we hold it, and we treat the
whole receipt as sensitive because of it.

### Information collected automatically

- **Server logs.** Requests to the service are logged with an IP address, a
  timestamp and a trace identifier, to run and secure the service. Retained for
  {{LOG_RETENTION}}.
- **Failed sign-in counters.** To stop password guessing, we keep a count of
  recent failed attempts against an irreversible fingerprint of the requesting
  address. We do not store the address itself for this purpose.

### What we do not collect

We want to be exact about this, because it is unusual:

- **No analytics.** There is no analytics SDK in the app and no event
  collection. We do not know which screens you use.
- **No advertising and no tracking.** No advertising SDK, no cross-app or
  cross-site tracking, no advertising identifier.
- **No crash reports are sent to us.** The app keeps recent errors on your
  device to help support conversations; it does not transmit them.
- **No location data.** We do not request or use device location. A store
  address may appear on a receipt, but we do not track where you are.
- **No contacts, no calendar, no microphone.**

## Permissions the app asks for

- **Camera** — to photograph a receipt. Declining it leaves gallery import
  working; you are not blocked.
- **Photo library** — to import a receipt you already photographed. We read
  only the images you pick.

## How we use your information

- To read your receipts and file them into your household
- To show you totals, trends and collections built from those receipts
- To compare prices of things you buy repeatedly, using **your household's own
  receipts**
- To run the shared shopping list
- To let you sign in, stay signed in, and recover access
- To keep the service secure, including rate-limiting sign-in attempts
- To respond to you when you contact us
- To meet legal obligations

We do not use your receipts to build advertising profiles, and we do not sell
your information.

### Legal bases (where the GDPR, UK GDPR or a similar regime applies)

- **Performance of a contract** — running the account and household features
  you signed up for
- **Legitimate interests** — keeping the service secure and working, provided
  that does not override your rights
- **Consent** — anything optional, which you can withdraw at any time
- **Legal obligation** — where the law requires us to keep or produce something

## OCR and automated extraction

Reading your receipt is automated, and it happens **on our own server**. We use
a local optical character recognition engine (RapidOCR running on ONNX
Runtime). Your receipt images and their contents are **not sent to any
third-party OCR provider, cloud vision API, or AI model**, and no external
provider trains on your receipts.

Automated reading is imperfect. It misreads totals, dates, and line items,
particularly on creased, faded or poorly lit receipts. Because of this:

- We mark fields we read with low confidence so you can check them
- We show you the original photograph beside the extracted values
- Your correction always overrides our reading
- No automated decision is made about you that has a legal or similarly
  significant effect

Do not rely on extracted figures for tax, accounting, warranty or reimbursement
purposes without checking them against the receipt itself.

## Who can see your receipts

**People in your household can.** This is what a household is for. Specifically:

- When you file a receipt into a household, every approved member of that
  household can see it, including its line items and its photograph.
- Joining a household is a **request**, not access. Nothing in a household is
  visible to someone until an owner or admin approves them.
- An owner or admin can see who is in the household and who has asked to join,
  including their name and email address.
- If you are removed from a household, you immediately lose access to it.
  Receipts you filed **stay with the household** — they belong to the shared
  ledger, not to you personally. Consider this before filing a receipt you
  would not want the household to keep.
- Nothing is shared **between** households. There is no pooled or crowd-sourced
  price database, and no user can see another household's data.

## Service providers

We deliberately use very few.

| Provider | What they do | What they can see |
|---|---|---|
| Cloudflare | Routes traffic to our server and encrypts it in transit | Connection metadata: IP address, timing, requested address. Encrypted request contents pass through their network |
| {{HOSTING_LOCATION}} hosting | The physical server we run | Everything, as the operator of the machine |

We do **not** use a third-party analytics provider, crash-reporting provider,
advertising network, OCR vendor, AI provider, email provider or payment
provider. If that changes, we will update this policy before the change ships.

## Where your information is stored

Receipt Hub runs on a single self-hosted server located in
{{HOSTING_LOCATION}}. Your account details, receipts and extracted receipt data
are stored there. Receipt images are stored as files on that server; the
database is SQLite.

Cloudflare operates a global network, so traffic to and from the service may be
routed through infrastructure outside Australia in transit. Contents are
encrypted in transit. We do not otherwise transfer your information overseas.

## Security

- **In transit:** HTTPS only. The app refuses unencrypted connections outright.
- **Passwords:** hashed with argon2id. We never store or log them.
- **Sessions:** signed bearer tokens with an expiry. Your household membership
  is re-checked on every request, so removing someone takes effect immediately.
- **Receipt images:** served only to authenticated members of the owning
  household, and marked `private, no-store` so they are not cached by
  intermediaries.
- **Separation between households:** enforced by the server on every query. A
  request for another household's receipt is refused.
- **At rest:** the database and images sit on the server's filesystem.
  Encryption at rest depends on that host's disk encryption.

No system is perfectly secure, and we do not claim otherwise.

## How long we keep things

| Data | How long |
|---|---|
| Account details | While your account exists |
| Receipt images and extracted data | Until you delete the receipt, or the household is deleted |
| Shopping list items | Until deleted |
| Server logs | {{LOG_RETENTION}} |
| Backups | {{BACKUP_RETENTION}} |
| Failed sign-in counters | A short rolling window, then discarded |

When you delete something it is removed from the live service promptly. It may
persist in backups until those backups rotate out, which is why
{{BACKUP_RETENTION}} matters and must be stated accurately.

Where the law requires us to keep something — for example a record we must
retain to comply with a legal obligation — we keep only that, only for as long
as required, and only for that purpose.

## Your rights

You can, at any time:

- **See your information.** Your receipts and account details are visible in
  the app.
- **Export it.** Account → Your data → Export this household gives you a CSV
  of every receipt and line item in the household.
- **Correct it.** Receipt fields are editable in the app. To change your name
  or email address, contact {{PRIVACY_EMAIL}} — self-service editing of account
  details is not available yet.
- **Delete a receipt.** From the receipt itself.
- **Delete your account.** Account → Your data → Delete my account, or see
  [Account deletion]({{PUBLIC_DOMAIN}}/account/delete). Receipts you filed stay
  with the household.
- **Withdraw consent** for anything you consented to.
- **Complain.** Write to {{PRIVACY_EMAIL}} and we will respond.

Depending on where you live you may also have the right to object to or
restrict certain processing, to data portability, and not to be discriminated
against for exercising a privacy right. We honour these regardless of where you
live.

We will not charge you for making a request, and we will not make you create an
account or use the app to make one.

### If you are unhappy with our response

- **Australia:** the Office of the Australian Information Commissioner, at
  oaic.gov.au
- **EU/EEA:** your national data protection authority
- **UK:** the Information Commissioner's Office, at ico.org.uk

You may complain to a regulator without contacting us first, though we would
rather have the chance to fix it.

## Marketing

We do not send marketing email. We have no email delivery at all at present, so
the only messages you receive from us are ones you ask for by contacting us
directly. If we introduce marketing email, it will be opt-in and every message
will carry an unsubscribe link.

## Cookies and tracking

The app does not use cookies. See [Cookies]({{PUBLIC_DOMAIN}}/cookies) for what
the website uses.

## Children

Receipt Hub is not directed at children and we do not knowingly collect
information from anyone under 16. If you believe a child has created an
account, write to {{PRIVACY_EMAIL}} and we will delete it.

## Data breaches

If a breach occurs that is likely to result in serious harm, we will assess it
promptly, notify affected users and notify the regulators we are required to
notify, within the time limits that apply.

## Changes to this policy

If we change this policy we will update the "last updated" date. Where a change
materially affects how we handle your information, we will tell you in the app
before it takes effect, and where the law requires consent for the change we
will ask for it rather than assume it. Previous versions are available on
request.

## Questions

{{PRIVACY_EMAIL}}
