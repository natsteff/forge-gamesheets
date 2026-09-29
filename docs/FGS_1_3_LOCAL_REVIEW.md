# FGS 1.3 development review record

This records pre-publication development on top of Forge revision `d19cc28`.
It is a historical verification record, not the current publication status.

## Completed verification

- Forge: 817 tests passed, one skipped; full lint passed. Changed Python files
  pass formatting checks. A pre-existing formatting warning in unrelated
  `app/sheet_game_associations.py` was not changed.
- Studio: 23 tests passed; site packaging passed.
- Shared renderer: 24 tests passed; both pinned bundles rebuilt and synced.
  Pattern SVG/PDF tests cover Letter/A4 and portrait/landscape with footers.
- LiveSheet HTTP/service tests cover host-only updates in both modes, invite/
  claimed-player denial, foreign-origin refusal, bounds, reset, immutable source
  snapshots, independent checkbox indices, session isolation and expiry cleanup.
- Browser: Forge tracker creation, save/reload, LiveSheet launch and persistent
  decrement verified using disposable local data. Studio music starter controls
  verified. The owner subsequently confirmed Studio browser PDF download and
  FGS download/re-import.
- Visual PDF review using the PDF skill and Poppler passed for all four tracker
  appearances, paired music staves and hex paper, including footer clearance.
  Test outputs were outside the repositories; no real sheets/databases were used.

## Owner review

The isolated preview servers created during development are:

- Forge: `http://127.0.0.1:8768/sheet-designer` (disposable library/data).
- Studio: `http://127.0.0.1:8767/` (browser-only).

They exist only while the development servers are running. For the normal
local Docker installation, rebuild source rather than pull the old published image:

```sh
cd /Users/nate/Documents/Codex/Forge-GameSheets
docker compose up -d --build app
```

Expect the new Tracker/Paper pattern sections and New-sheet paper templates,
FGS version 1.3 when using either addition, and profile `fgs-page-1.3` in the
renderer manifest. A local source build may have a different build identity
from the published image.

To restart Studio development later (stop the existing server first):

```sh
cd /Users/nate/Documents/Codex/FGS-Studio
python3 -m http.server 8767 --bind 127.0.0.1
```

Review fixed/fill sizing, units, each tracker appearance, undo/redo, save/export/
import and PDF downloads in both editors. Print a pattern at actual size (100%)
if physical spacing matters. Health measurement logs remain separate future work.

## Publication procedure

The owner completed browser download/import checks and approved commit/push of
both repositories. Forge source must be committed first, then Studio's pinned
renderer source revision recorded before its commit. Verify Forge's image
publishing and Studio's GitHub Pages workflow, then test the published image on
Docker Test. Screenshots can be refreshed separately.
