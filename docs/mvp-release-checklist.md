# Receipts Hub MVP release checklist
Status: **implementation-ready, release-blocked only by device and operational verification**.

## Verified in this workspace
- Backend regression suite: `77 passed`.
- Flutter static analysis: clean.
- Flutter test suite: `44 passed`.
- Root ignore rules now exclude runtime data, secrets, databases, uploads, Python caches, and Flutter build output.
- Runtime data is outside the repository by default at `%LOCALAPPDATA%\GroceryHome`.

## Before calling the MVP released
1. Create or clone a real repository and commit the source-only starting point.
2. Back up the active runtime directory before any migration or deployment:
   `grocery_home.sqlite3`, SQLite WAL/SHM files, and `receipts\` must be captured together.
3. Run the backend with a generated `GROCERY_HOME_SESSION_SECRET` of at least 32 random characters. Keep `.env` outside version control.
4. Start the API on the private LAN and verify `/api/v1/health` from the Android device.
5. On a physical Android phone, test: connect → PIN auth → multi-page capture → upload → OCR polling → retry/manual fallback → review → file → Home/Receipts/Insights/List.
6. Verify the Docker stack with `docker compose config` and `docker compose up`; Docker was unavailable on the development workstation.
7. Profile receipt-list scrolling, image rendering, upload/OCR latency, and Riverpod rebuilds.
8. Complete accessibility checks with large text, contrast, reduced motion, back navigation, and a smaller phone.
9. Build and install a signed release APK only after the host backup/upgrade procedure is tested.

## Backup example (PowerShell)

Stop the host service first, then copy the complete runtime directory:

```powershell
$source = Join-Path $env:LOCALAPPDATA 'GroceryHome'
$destination = Join-Path $env:USERPROFILE 'Backups\GroceryHome\' + (Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
```

Restore only with the service stopped, replacing the complete runtime directory. Keep at least one tested, offline copy.
