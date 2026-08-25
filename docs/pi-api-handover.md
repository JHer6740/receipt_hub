# Handover: running the Receipts Hub API on the Raspberry Pi

Everything needed to stand the API up on the Pi and serve it over HTTPS through
Cloudflare, written for whoever does the work — not necessarily the person who
wrote the code.

Read [§1 Blockers](#1-read-this-first-two-blockers) before starting. One of
them may decide whether the Pi is viable at all.

- **Service:** FastAPI + SQLite + local OCR, one process
- **Public address:** `https://receipts.aacu-church.org` (substitute your own)
- **Repository:** `receipts - grocery home/` in this workspace
- **Companion docs:** [deployment](deployment.md) for the app build,
  [legal drafts](legal/) for the pages the stores require

---

## 1. Read this first: two blockers

### 1.1 Python 3.12 or newer is required

`pyproject.toml` sets `requires-python = ">=3.12"`.

**Raspberry Pi OS (Bookworm) ships Python 3.11.** The install will refuse.
Check before anything else:

```bash
python3 --version
```

If it reports 3.11, pick one:

| Option | Notes |
|---|---|
| Raspberry Pi OS **Trixie** | Ships Python 3.13. Cleanest option, but a full OS upgrade |
| Build 3.12+ from source | ~30–60 min on a Pi 4/5, and you own the maintenance |
| `pyenv` | Also compiles from source; easier to manage more than one version |
| Relax `requires-python` to 3.11 | **Only after running the test suite on 3.11.** The code uses `match`, PEP 604 unions and `dict[str, X]`, which are fine on 3.11, but nothing has been tested there. Do not do this blind |

Do not skip this by using a container unless you are willing to also solve
§1.2 inside the container.

### 1.2 OCR on ARM is unproven here

The service reads receipts with RapidOCR on ONNX Runtime. That is the whole
point of the product, and it is the part most likely to disappoint on a Pi.

Two separate risks:

**Does it install?** The `ocr` extra needs `onnxruntime`, `rapidocr`,
`pypdfium2` and `pillow-heif` wheels for `aarch64` on your Python version. If a
wheel is missing, pip tries to build from source and will probably fail.

**Is it fast enough?** A Pi is far slower than the development machine. The app
polls with a **three-minute budget** and then shows a failure. If a single
receipt takes longer than that on the Pi, capture is broken from the user's
point of view even though nothing is technically wrong.

**Measure it before you commit to the Pi** (§7.4). If it is too slow, the
options are: a faster machine, a smaller detection model, or moving OCR off the
Pi — all bigger decisions than this document covers.

The service will start and run without the OCR extra. Uploads will fail at the
reading stage, and the app will show its "could not read this receipt" state
with manual entry offered — which is honest, but not a product.

---

## 2. What you are deploying

```
phone ──HTTPS──> Cloudflare ──tunnel──> cloudflared ──HTTP──> uvicorn 127.0.0.1:8000
                                          (on the Pi)              │
                                                                   ├── SQLite database
                                                                   ├── receipt images (files)
                                                                   └── OCR worker (same process)
```

One process serves the JSON API at `/api/v1`, the existing browser interface,
and a durable background worker that does the OCR. The worker starts with the
app — there is nothing separate to run.

Cloudflare terminates TLS, so **the Pi needs no certificate and no open
inbound port.** The tunnel dials out.

---

## 3. Prepare the Pi

```bash
sudo apt update
sudo apt install -y git python3-venv python3-dev build-essential libjpeg-dev zlib1g-dev
```

`libjpeg-dev` and `zlib1g-dev` are for Pillow. `build-essential` and
`python3-dev` are needed if any dependency has to compile.

Create a service account that owns nothing else:

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin receiptshub
```

---

## 4. Install

```bash
sudo -u receiptshub -H bash
cd ~
git clone <your-fork-or-this-repo> receipts-hub
cd "receipts-hub/receipts - grocery home"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install -e ".[ocr]"
```

If `[ocr]` fails, install the base package so you at least have a running
service, and come back to §1.2:

```bash
.venv/bin/pip install -e .
```

Confirm OCR actually imported, rather than assuming:

```bash
.venv/bin/python -c "import onnxruntime, rapidocr; print('OCR available')"
```

---

## 5. Configure

Runtime data lives outside the checkout so a `git pull` can never touch it. On
Linux the default is `~/.local/share/GroceryHome`; set it explicitly anyway.

```bash
sudo -u receiptshub mkdir -p /home/receiptshub/data
```

Create `/home/receiptshub/receipts-hub.env`, owned by the service user and
readable only by it:

```ini
GROCERY_HOME_DATA_DIR=/home/receiptshub/data
GROCERY_HOME_SESSION_SECRET=<paste a 48+ character random string>
GROCERY_HOME_SECURE_COOKIES=true
GROCERY_HOME_TIMEZONE=Australia/Sydney
GROCERY_HOME_CURRENCY=AUD
```

```bash
openssl rand -base64 48          # generate the secret
sudo chown receiptshub:receiptshub /home/receiptshub/receipts-hub.env
sudo chmod 600 /home/receiptshub/receipts-hub.env
```

**`GROCERY_HOME_SESSION_SECRET` matters.** Every session token is signed with
it. If it is absent one is generated and persisted, but setting it explicitly
means you control it and can rotate it. **Rotating it signs everyone out.**
Never commit it — this repository is public.

**`GROCERY_HOME_SECURE_COOKIES=true`** because Cloudflare serves over HTTPS.

Other settings you are unlikely to need, all `GROCERY_HOME_`-prefixed:
`DATABASE_URL`, `SESSION_COOKIE`, `SESSION_MAX_AGE`, `MAX_UPLOAD_BYTES`
(default 20 MB), `MAX_PHOTO_FILES` (5), `MAX_PDF_PAGES` (10),
`PIN_MAX_FAILURES` (5), `PIN_WINDOW_SECONDS`, `PIN_LOCK_SECONDS`.

---

## 6. First run

### 6.1 Back up first, if there is anything to lose

**If you are moving an existing database onto the Pi, back it up before the
first start.** Schema migration 2 adds accounts and multi-tenancy, and it
*rebuilds the `households` table* to drop a constraint. It is written to be
safe and idempotent, but a rebuild is a rebuild.

```bash
tar czf pre-migration-$(date +%Y%m%d-%H%M%S).tar.gz \
  grocery_home.sqlite3 grocery_home.sqlite3-wal grocery_home.sqlite3-shm receipts/
```

Copy it **off the Pi** before continuing.

### 6.2 Start it once by hand

```bash
sudo -u receiptshub -H bash
cd "/home/receiptshub/receipts-hub/receipts - grocery home"
set -a; . /home/receiptshub/receipts-hub.env; set +a
.venv/bin/python -m uvicorn grocery_home.app:app --host 127.0.0.1 --port 8000
```

The schema is created and migrated on startup. Expect:

- No error on boot
- `curl -s localhost:8000/api/v1/health` returning `{"status":"ok",...}`

You may see: *"No household PIN is set, so the browser interface cannot be
signed into."* **That is fine and expected.** The PIN is only for the old
browser interface. The mobile app signs in with an email and password. Only run
`grocery-home setup` if you actually want the browser UI, and never with
`--skip-import` omitted unless you intend to import the legacy archive.

Stop it with Ctrl-C once health responds.

---

## 7. Run it as a service

`/etc/systemd/system/receipts-hub.service`:

```ini
[Unit]
Description=Receipts Hub API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=receiptshub
Group=receiptshub
WorkingDirectory=/home/receiptshub/receipts-hub/receipts - grocery home
EnvironmentFile=/home/receiptshub/receipts-hub.env
ExecStart=/home/receiptshub/receipts-hub/receipts - grocery home/.venv/bin/python -m uvicorn grocery_home.app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

# The service needs nothing outside its own data directory.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/receiptshub/data

[Install]
WantedBy=multi-user.target
```

The directory name contains spaces. systemd accepts them in `WorkingDirectory`
and `ExecStart` as written above, but if anything misbehaves, the cleanest fix
is to rename the checkout directory to something without spaces.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now receipts-hub
systemctl status receipts-hub
journalctl -u receipts-hub -f
```

Bind to `127.0.0.1`, never `0.0.0.0`: the tunnel is the only intended way in.

---

## 8. Expose it through Cloudflare

Add an ingress rule alongside the existing project, most specific first:

```yaml
# ~/.cloudflared/config.yml
tunnel: <existing tunnel id>
credentials-file: /root/.cloudflared/<id>.json

ingress:
  - hostname: receipts.aacu-church.org
    service: http://localhost:8000
  # ... the existing project's rules ...
  - service: http_status:404
```

```bash
cloudflared tunnel route dns <tunnel-name> receipts.aacu-church.org
sudo systemctl restart cloudflared
```

Then, in the Cloudflare dashboard for that hostname:

- **SSL/TLS mode:** Full. The origin is plain HTTP inside the tunnel, which is
  fine — the tunnel is the encrypted channel.
- **Do not enable "Always Use HTTPS" only**; also leave HTTP→HTTPS redirects
  on so a mistyped `http://` never reaches the API in the clear.
- **Caching:** leave off for `/api/*`. Receipt images are already sent
  `Cache-Control: private, no-store`, but caching an authenticated API is a
  bad idea regardless.
- **Upload size:** receipts can be up to 20 MB per file and five files per
  receipt. Check the plan's request-size limit — the free plan's 100 MB is
  fine, but a proxy limit lower than 20 MB will break uploads.

---

## 9. Verify it end to end

Do all four. The first three prove the API; the fourth is the one that
actually matters.

### 9.1 Reachable and encrypted

```bash
curl -s https://receipts.aacu-church.org/api/v1/health
# {"status":"ok","service":"grocery-home",...}
```

### 9.2 An account can be created and used

```bash
BASE=https://receipts.aacu-church.org/api/v1

TOKEN=$(curl -s -X POST $BASE/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"a-long-enough-password","display_name":"You"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["token"])')

# A household to file receipts into, and a token scoped to it
SCOPED=$(curl -s -X POST $BASE/households \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Test household"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["session"]["token"])')

curl -s $BASE/receipts -H "Authorization: Bearer $SCOPED"
# {"success":true,"data":{"items":[],"pagination":{...}}}
```

### 9.3 Tenancy holds

An account with no household must be refused, not served an empty ledger:

```bash
curl -s -o /dev/null -w '%{http_code}\n' $BASE/receipts \
  -H "Authorization: Bearer $TOKEN"
# 409 — NO_HOUSEHOLD_SELECTED
```

### 9.4 A real receipt, timed

This is the acceptance test for the Pi.

```bash
time curl -s -X POST $BASE/uploads \
  -H "Authorization: Bearer $SCOPED" \
  -F "files=@/path/to/a/real/receipt.jpg"
# returns a batch_id

# Poll until it settles, and time the whole thing
curl -s $BASE/uploads/<batch_id> -H "Authorization: Bearer $SCOPED"
```

**Write down how long it took, end to end.** Then compare:

| Result | What it means |
|---|---|
| Under ~20s | Comfortable |
| 20s – 3min | Works, but feels slow. Consider a progress-expectation change in the app |
| Over 3 min | **The app gives up.** The Pi is not viable for OCR as configured |

Check the extracted merchant, date and total against the paper. A fast wrong
answer is worse than a slow right one.

---

## 10. Backups

The database and the receipt images must be captured **together**, or they will
disagree about which receipts exist.

`/usr/local/bin/receipts-hub-backup`:

```bash
#!/bin/bash
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
DEST=/home/receiptshub/backups
mkdir -p "$DEST"
systemctl stop receipts-hub
tar czf "$DEST/receipts-hub-$STAMP.tar.gz" -C /home/receiptshub/data .
systemctl start receipts-hub
find "$DEST" -name 'receipts-hub-*.tar.gz' -mtime +30 -delete
```

```bash
sudo chmod +x /usr/local/bin/receipts-hub-backup
# Nightly at 03:15
echo '15 3 * * * root /usr/local/bin/receipts-hub-backup' | sudo tee /etc/cron.d/receipts-hub-backup
```

Two things this does not do, and you should:

- **Copy backups off the Pi.** An SD card is not a backup. Sync to another
  machine or to storage you control.
- **Restore one.** A backup you have never restored is a hope. Try it on a
  copy before you need it.

Whatever retention you settle on here is the answer to `{{BACKUP_RETENTION}}`
in the [legal drafts](legal/) — the privacy policy has to state how long
deleted data survives in backups, and it has to be true.

---

## 11. Upgrading

```bash
sudo -u receiptshub -H bash
cd "/home/receiptshub/receipts-hub/receipts - grocery home"
git pull
.venv/bin/pip install -e ".[ocr]"
exit
sudo systemctl restart receipts-hub
journalctl -u receipts-hub -n 50
```

Migrations run automatically on start and are forward-only — **there is no
downgrade.** Back up before upgrading across a schema change, and check
`journalctl` for migration errors rather than assuming success.

---

## 12. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ERROR: Package requires a different Python` on install | §1.1. Python is 3.11 |
| Service starts, uploads never leave "Reading receipt" | OCR extra not installed, or the worker is failing. Check `journalctl -u receipts-hub` |
| App shows "Receipts Hub is not responding" | Tunnel down (`systemctl status cloudflared`), or the app is built against the wrong `RECEIPTS_HUB_API_BASE_URL` |
| App reaches the service but every request is 401 | `GROCERY_HOME_SESSION_SECRET` changed, which invalidates every issued token. Everyone signs in again |
| Uploads fail on large photos | Cloudflare request-size limit below 20 MB, or `GROCERY_HOME_MAX_UPLOAD_BYTES` |
| Receipt images 404 in the app | Data directory moved without the images, or `GROCERY_HOME_DATA_DIR` differs between setup and service |
| `sqlite3.OperationalError: database is locked` | Two processes on one database. Only one service instance and one worker are supported |
| Browser interface asks for a PIN you never set | Expected. The browser UI needs `grocery-home setup`; the mobile app does not |

Logs: `journalctl -u receipts-hub -f`. Every API error carries a trace id that
also appears in the log, so quote it when reporting a problem.

---

## 13. What this deployment is not

Stated plainly so nobody discovers it in production:

- **SQLite, single writer.** Fine for a few households. Concurrent writes from
  several active households will contend, and the fix is Postgres.
- **Receipt images are files on the Pi.** No object storage, no replication.
  Their durability is exactly your backup discipline.
- **Encryption at rest depends on the SD card / disk.** The application does
  not encrypt the database or the images. If the card is stolen, the receipts
  are readable. The [privacy policy draft](legal/privacy-policy.md) says this;
  keep it true, or enable disk encryption and update it.
- **No email.** Password reset accepts an address and reports success but sends
  nothing. Email verification does not exist. So there is currently **no
  account recovery** — a forgotten password means a manual database fix.
- **No monitoring or alerting.** If the service dies, systemd restarts it; if it
  dies repeatedly, nothing tells you.
- **One machine, no redundancy.** Power loss or a dead SD card is an outage.
- **No rate limiting in front of the service.** The API throttles auth attempts
  itself, but Cloudflare rules would be a better first line.

---

## 14. Handover checklist

Setup:

- [ ] Python 3.12+ confirmed (§1.1)
- [ ] `[ocr]` extra installed and imports verified (§4)
- [ ] `GROCERY_HOME_SESSION_SECRET` set, 48+ chars, stored somewhere safe, not in git
- [ ] `GROCERY_HOME_SECURE_COOKIES=true`
- [ ] Data directory outside the checkout
- [ ] Env file `chmod 600`, owned by the service user
- [ ] systemd unit enabled, survives `sudo reboot`
- [ ] Bound to `127.0.0.1` only
- [ ] Cloudflare hostname routed, caching off for `/api/*`
- [ ] Pre-migration backup taken and copied off the Pi

Verified:

- [ ] `/api/v1/health` over HTTPS (§9.1)
- [ ] Register → create household → list receipts (§9.2)
- [ ] Account with no household is refused with 409 (§9.3)
- [ ] **A real receipt uploaded, read, and timed (§9.4)** — with the number
      written down
- [ ] Extracted merchant, date and total checked against the paper receipt
- [ ] Nightly backup runs, and one has been restored to a scratch copy
- [ ] Backups copied off the Pi

Decided, and fed back into the docs:

- [ ] Backup retention → `{{BACKUP_RETENTION}}` in [legal drafts](legal/)
- [ ] Log retention → `{{LOG_RETENTION}}`
- [ ] Hosting location → `{{HOSTING_LOCATION}}`
- [ ] Whether OCR on the Pi is fast enough to ship
