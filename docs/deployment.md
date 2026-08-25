# Deploying Receipts Hub

Target for the first commercial release: the existing Raspberry Pi, reached
over HTTPS through Cloudflare on a subdomain of `aacu-church.org`.

This document assumes the Pi already runs another project behind a Cloudflare
tunnel, so the tunnel and DNS pattern are established.

## 1. Pick the subdomain

Everything below uses `receipts.aacu-church.org`. Substitute whatever you
actually create — the value is configuration, not code, and appears in exactly
three places:

| Where | Why |
|---|---|
| `--dart-define=RECEIPTS_HUB_API_BASE_URL` | The address the app talks to |
| `android/key.properties` → `appLinkHost` | The App Link host in the manifest |
| `/.well-known/assetlinks.json` on that host | Proves the app may own those links |

## 2. HTTPS

Cloudflare terminates TLS, so the Pi does **not** need its own certificate:
the tunnel connects outbound and the origin can stay plain HTTP on localhost.

```
phone ──HTTPS──> Cloudflare ──tunnel──> cloudflared on the Pi ──HTTP──> uvicorn:8000
```

Add an ingress rule alongside the existing project:

```yaml
# ~/.cloudflared/config.yml
ingress:
  - hostname: receipts.aacu-church.org
    service: http://localhost:8000
  # ... the existing project's rules ...
  - service: http_status:404
```

The app refuses cleartext (`android/app/src/main/res/xml/network_security_config.xml`),
so it will only talk to the `https://` hostname. That is the intended
behaviour — do not add an exception to reach the Pi directly by IP.

## 3. Run the service

> Setting the Pi up from scratch is covered step by step in
> [the Pi API handover](pi-api-handover.md), including two blockers worth
> reading first: Raspberry Pi OS ships Python 3.11 and the service needs 3.12+,
> and OCR speed on ARM is unmeasured. The summary below assumes those are
> settled.

```bash
# On the Pi, from `receipts - grocery home`
export GROCERY_HOME_SESSION_SECRET="$(openssl rand -base64 48)"   # keep this out of git
python -m uvicorn grocery_home.app:app --host 127.0.0.1 --port 8000
```

Bind to `127.0.0.1`, not `0.0.0.0`: the tunnel is the only way in, so there is
no reason to listen on the LAN as well.

Schema migrations apply on startup (`initialize_schema`), including migration 2
which adds accounts and tenancy. **Back up `grocery_home.sqlite3` plus its
`-wal`/`-shm` files and the `receipts/` directory before the first run on real
data** — migration 2 rebuilds the `households` table.

## 4. Build the app against it

```bash
flutter build apk --release \
  --dart-define=RECEIPTS_HUB_API_BASE_URL=https://receipts.aacu-church.org \
  --dart-define=RECEIPTS_HUB_PRIVACY_URL=https://receipts.aacu-church.org/privacy \
  --dart-define=RECEIPTS_HUB_TERMS_URL=https://receipts.aacu-church.org/terms \
  --dart-define=RECEIPTS_HUB_PRIVACY_CHOICES_URL=https://receipts.aacu-church.org/privacy/choices \
  --dart-define=RECEIPTS_HUB_ACCOUNT_DELETION_URL=https://receipts.aacu-church.org/account/delete \
  --dart-define=RECEIPTS_HUB_COOKIES_URL=https://receipts.aacu-church.org/cookies \
  --dart-define=RECEIPTS_HUB_SUPPORT_EMAIL=support@aacu-church.org
```

The privacy and terms rows stay hidden in Account until those URLs are set, so
a build without them shows nothing rather than a dead link.

All five pages must exist before submitting to either store. Drafts are in
[docs/legal](legal/), each with the placeholders it still needs resolved. Apple
and Google both reject on a missing or unreachable privacy policy, and Google
additionally requires the account-deletion page to be reachable **without** the
app installed.

## 5. App Links

Needed so an email verification or password reset link opens the app instead of
a browser. Two halves, and both are required:

1. `android/key.properties` → `appLinkHost=receipts.aacu-church.org`
2. Serve this from the subdomain, using the **release** signing certificate's
   SHA-256 fingerprint:

```bash
keytool -list -v -keystore receipts-hub-upload.jks -alias upload | grep SHA256
```

```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.receiptshub.receipts_hub",
    "sha256_cert_fingerprints": ["<the SHA256 from above>"]
  }
}]
```

It must be served at `https://receipts.aacu-church.org/.well-known/assetlinks.json`
as `application/json` with no redirect. Until it is, Android treats the links as
ordinary web links — the app still works, the links just open a browser.

## 6. What is still missing before this is a product

Named plainly rather than left to be discovered:

- **No release signing key yet.** `android/key.properties` does not exist, so a
  release build warns and falls back to debug keys. It cannot be uploaded to
  Play, and App Links cannot be verified, until you create and back up a
  keystore. Losing that key means never being able to update the listing.
- **No email delivery.** Password reset validates the address and always
  reports success, but sends nothing. Email verification is not implemented at
  all, because without delivery nobody could obtain a token.
- **SQLite, not Postgres.** Fine for one household on a Pi; it is a single
  writer, so concurrent households will contend. Revisit when that hurts.
- **Receipt images are on the Pi's filesystem**, not object storage. They are
  served authenticated through the API, so this is a durability and backup
  concern rather than an access one.
- **OCR on ARM.** The service does OCR with ONNX Runtime / RapidOCR. On a Pi
  this will be markedly slower than on the development machine, and the arm64
  wheels need to be available for the installed Python. Measure a real receipt
  end to end before assuming the capture flow feels acceptable — the app polls
  with a three-minute budget, and a slow Pi could exceed it.
- **No crash reporting backend.** `lib/core/data/error_reporter.dart` captures
  and keeps recent errors behind one seam; plugging in a provider is a
  one-function change once an account exists.

## 7. Backup

Stop the service, then copy the runtime directory whole — the database and the
receipt images have to be captured together or they will disagree:

```bash
sudo systemctl stop receipts-hub
tar czf "receipts-hub-$(date +%Y%m%d-%H%M%S).tar.gz" \
  grocery_home.sqlite3 grocery_home.sqlite3-wal grocery_home.sqlite3-shm receipts/
sudo systemctl start receipts-hub
```

Keep at least one copy off the Pi. An SD card is not a backup.
