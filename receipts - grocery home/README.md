# Grocery Home

Grocery Home is a private, mobile-friendly family app for receipt uploads,
shared shopping lists, spending trends and likely-needed grocery suggestions.
It runs on one Windows PC and is available to phones and tablets on the same
private network.

The app keeps receipt OCR, images, PDFs and household data on the host PC.
It uses FastAPI, server-rendered pages, SQLite and a single Uvicorn process;
there is no Node or React build step.

## What it does

- Accepts receipt photos and PDFs, then tracks extraction as a durable job.
- Parses known Woolworths and BIG W layouts and offers a correction flow for
  photos, scans and unfamiliar Coles, Aldi or IGA layouts.
- Preserves duplicate uploads for audit while excluding them from spending.
- Shows grocery spend, category and product-price trends without exposing
  partially rebuilt analytics.
- Maintains one shared, checkable shopping list plus predicted needs.
- Runs OCR locally. A weekly Woolworths price refresh sends product
  descriptions, not receipt images, to Woolworths and retains stale quotes if
  the unofficial endpoint is unavailable.

## Requirements

- Windows 10 or 11 on a trusted private home network.
- Python 3.12 or newer.
- A PC that can remain awake while family members use the app.
- Administrator access once, if Windows Firewall needs an inbound rule.

## Install and set up

Open PowerShell in this project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[ocr]"
.\start_grocery_home.ps1 -Setup
```

Setup asks for a household name and shared PIN without echoing the PIN. It
creates the database, stores a generated session-signing secret in that
database, copies the legacy PDFs to managed private storage, and builds the
first analytics snapshot. The legacy import verifies these locked counts:

- 103 upload records
- 100 canonical receipts
- 3 duplicate relationships
- 752 canonical receipt items

Setup is safe to rerun. It retains an existing PIN unless you explicitly
choose to replace it, and the importer does not modify or delete the source
PDFs, CSVs, dashboard or analysis outputs. Replacing the PIN signs out existing
browser sessions.

To create an empty household, omit the history with:

```powershell
.\.venv\Scripts\python.exe -m grocery_home.cli setup --skip-import
```

If the legacy files live in another checkout, point setup at the directory
that contains `receipts\` and `parsed\`:

```powershell
.\.venv\Scripts\python.exe -m grocery_home.cli setup `
  --legacy-root "D:\Data\receipts-project"
```

## Start the app

```powershell
.\start_grocery_home.ps1
```

On the host PC, open <http://127.0.0.1:8000>. Keep that PowerShell window open;
press `Ctrl+C` to stop the app cleanly. The launcher always uses one web
process, which also coordinates the durable background worker.

### Allow private-LAN access

First confirm that the active home connection is marked `Private`, not
`Public`:

```powershell
Get-NetConnectionProfile
```

Only on a network you trust, open PowerShell **as Administrator** and add a
private-profile, local-subnet-only firewall rule:

```powershell
New-NetFirewallRule `
  -DisplayName "Grocery Home (private LAN)" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8000 `
  -Profile Private `
  -RemoteAddress LocalSubnet
```

Find the host PC's private IPv4 address:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object {
    $_.IPAddress -notlike "127.*" -and
    $_.IPAddress -notlike "169.254.*"
  } |
  Select-Object InterfaceAlias, IPAddress
```

From a phone on the same Wi-Fi, visit `http://<private-ip>:8000`, such as
`http://192.168.1.25:8000`, and enter the shared PIN. Do not create a router
port-forward for port 8000.

To remove the firewall rule later, use an elevated PowerShell:

```powershell
Remove-NetFirewallRule -DisplayName "Grocery Home (private LAN)"
```

If port 8000 is already in use, choose another port in both the launcher and
firewall rule:

```powershell
.\start_grocery_home.ps1 -Port 8123
```

## Data and configuration

Runtime data defaults to:

```text
%LOCALAPPDATA%\GroceryHome\
├── grocery_home.sqlite3
├── receipts\
└── tmp\
```

New receipt files are deliberately kept out of the OneDrive project folder.
Raw receipts are served only through authenticated application routes, never
from the public static directory.

Use another location either with the launcher or an environment variable:

```powershell
.\start_grocery_home.ps1 -DataDir "D:\Private\GroceryHome"

$env:GROCERY_HOME_DATA_DIR = "D:\Private\GroceryHome"
.\start_grocery_home.ps1
```

The most useful environment settings are:

| Setting | Default | Purpose |
| --- | --- | --- |
| `GROCERY_HOME_DATA_DIR` | `%LOCALAPPDATA%\GroceryHome` | Database and managed receipt storage |
| `GROCERY_HOME_DATABASE_URL` | SQLite in the data directory | Advanced SQLAlchemy database override |
| `GROCERY_HOME_SESSION_SECRET` | Generated and stored locally | Optional signing-secret override; use at least 32 characters |
| `GROCERY_HOME_TIMEZONE` | `Australia/Sydney` | Household dates and forecasts |
| `GROCERY_HOME_CURRENCY` | `AUD` | Household currency |
| `GROCERY_HOME_SECURE_COOKIES` | `false` | Set `true` only when serving through HTTPS |

An explicit `--data-dir` launcher argument takes precedence over the default
SQLite location. Avoid combining it with a custom
`GROCERY_HOME_DATABASE_URL`.

### OCR dependencies

The recommended `.[ocr]` install includes RapidOCR/ONNX, HEIC support and PDF
rendering for local photo and scanned-PDF extraction. A minimal install can
parse supported text PDFs but cannot complete the full photo workflow:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Add local OCR later with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ocr]"
```

## Privacy and security

Grocery Home uses a shared household PIN, Argon2 PIN hashing, signed
HttpOnly/SameSite cookies, CSRF protection and persistent login throttling.
Receipt storage and OCR stay on the PC.

Version 1 uses plain LAN HTTP. The PIN prevents casual access but **does not
encrypt network traffic**; another party able to observe the home network may
see traffic. Use only a trusted private network and never expose the port to
the public internet. Set `GROCERY_HOME_SECURE_COOKIES=true` only after putting
the app behind a correctly configured HTTPS endpoint.

Weekly live pricing is Woolworths-only. The refresh sends active or needed
product descriptions to Woolworths' unofficial endpoint; no receipt image or
PDF is sent. Other-retailer prices come from the family's paid-price history.

## Back up household data

Stop Grocery Home before copying the data directory so the SQLite database and
its write-ahead log are consistent. Then use a private backup destination:

```powershell
$GroceryHomeData = Join-Path $env:LOCALAPPDATA "GroceryHome"
$BackupStamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item `
  -LiteralPath $GroceryHomeData `
  -Destination "D:\PrivateBackups\GroceryHome-$BackupStamp" `
  -Recurse
```

The backup contains spending history, the hashed PIN, signing secret and raw
receipts, so protect it like the originals. Restore only while the app is
stopped. The original OneDrive PDFs are not a substitute for this backup
because new uploads live only in the runtime data directory.

## Development

Install all development and OCR dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ocr,dev]"
```

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run a focused module or coverage report:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_importer.py
.\.venv\Scripts\python.exe -m pytest --cov=grocery_home --cov-report=term-missing
```

For browser tests, install the Playwright browser once:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Use a disposable data directory for manual development:

```powershell
$env:GROCERY_HOME_DATA_DIR = "$PWD\.dev-data"
.\.venv\Scripts\python.exe -m grocery_home.cli setup --skip-import
.\.venv\Scripts\python.exe -m grocery_home.cli serve
```
