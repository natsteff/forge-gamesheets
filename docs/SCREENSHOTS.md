# README screenshot maintenance

## Current set

Core feature screenshots were last captured September 15, 2026. The demo uses invented games
(Lantern Vale, Pebble Parade,
Pocket Orchard, Starship Signals), original sample PDFs and simple cover art,
example-only resource URLs, and disposable demo accounts. No token was captured.
The cropped BGG integration image uses a public Carcassonne association solely
to demonstrate verified controls; it contains no private library data. The build
panel correctly says Local development build: this was a local source run, not
a published-container verification.

The gallery does not yet include dedicated current captures for LiveSheets,
GameSheet-to-game association and rendered previews, the Sheet Designer About
dialog, or FGS 1.1 logo and Footer controls. Existing Designer and game-page
captures remain useful for their core layouts but predate those added controls.
Do not describe the gallery as complete coverage until the replacement captures
below have been created and inspected. Use only a disposable fictional sheet for
the logo/Footer capture; do not publish a personal game logo or author credit.

The README gallery contains library-overview, game-resources, assign-categories,
reprint-maintenance, users, activity-history, settings-build, sheet-designer,
sheet-designer-startup, sheet-designer-open, and bgg-integration PNGs in
`docs/images/`. The Sheet Designer
captures were supplied from the integrated local Forge build and show only the
invented default sheet content. The older desktop-navigation and mobile-navigation
files remain available for historical comparison but are omitted from the gallery
because they predate the top-level Sheet Designer link. The obsolete
`settings.png` and
`forge-reprint.png` captures were removed when global QR guest access and secure
token sharing were replaced by public-by-default, per-resource QR restrictions.
Capture replacement Settings and FORGE Reprint images after the interface is
finalized.

The former `bgg-manual.png` remains as a historical capture but was removed from
the public gallery on September 15 because it predates the unified
**BoardGameGeek integration** section. `bgg-integration.png` now replaces it and
shows the current verified-association, replacement search, manual URL override,
official attribution, and action layout. It contains no token or private path.

On September 15, the replacement BGG section was visually reviewed again from
current source using the fictional `Lantern Vale` fixture. The complete page
confirmed the resource-link divider, **BoardGameGeek integration** title,
official attribution, token-free manual fallback, and styled artwork file
control. The new Sheet Designer startup choice was also rendered and confirmed
to present **New sheet**, **Open sheets**, and **Resume last sheet** before the
editor. The in-app browser still exposed screenshot bytes only inside the
review session. User-supplied verified PNG captures subsequently provided the
repository artifacts for both the BGG section and Designer startup page.

The Metadata portability page was visually reviewed September 14, 2026 using a
disposable empty library and synthetic Admin. Its navigation label and page do
not appear in any existing gallery image. Add a dedicated
`metadata-portability.png` only when a complete-page
capture can be saved and inspected; do not substitute a cropped viewport that
hides the import or folder-based discovery workflow.

## Repeatable capture checklist

1. Use a disposable demo directory outside the repository, with its own library
   and database. Generate original sample PDFs/artwork; never copy a personal
   library or use live account data. Start the current application on loopback
   with explicit demo library/data paths. Do not load the deployment's `.env`.
2. Bootstrap a disposable Admin and Reader in that demo only. Add a few category
   assignments and pinned resources. Leave all passphrase fields empty in captures.
3. Capture the gallery routes: `/`, `/games/{demo-id}`, `/assign-categories`,
   `/r/{demo-resource-id}`, `/history`, `/settings/reprints`, `/settings`,
   `/settings/users`, `/settings/metadata-portability`, `/games/{demo-id}/edit`,
   `/sheet-designer`, `/livesheets`, one LiveSheet setup page, and one active
   LiveSheet. Discover IDs from the demo; do not assume production IDs. Use an
   invented or default draft for Designer, Open Sheets, association, About, and
   LiveSheet captures.
4. On bulk categories, select games and a category to illustrate the controls;
   no change need be applied. Generate an ordinary demo reprint to show its ready
   state. Do not expose QR links from a live installation. Leave the BGG input
   empty rather than pretending an invented game has a real BGG listing.
   Associate one invented GameSheet with its invented game and capture the
   rendered GameSheet preview on the game page. Use only a disposable LiveSheet
   session and obscure or crop its invitation URL and QR code if they are visible.
5. Capture desktop and mobile navigation after major navigation changes. Confirm
   the top-level Sheet Designer link appears for the disposable Admin, capture the
   open Admin dropdown at desktop width, and capture the open hamburger menu at
   390 × 844. Restore any temporary viewport override afterward.
6. Inspect every saved PNG, not just the live browser. Check text, cropping,
   responsive wrapping, loaded fonts/previews, empty password fields, and absence
   of private paths, hostnames, tokens, or real account details. Section crops must
   retain the full explanation and controls. Update captions to match actual content.
7. Replace all affected images together with the README; run documentation tests,
   the full suite, and lint. Review the rendered gallery before publication. Stop
   the temporary server when finished. Do not commit demo databases or PDF files.

The next complete refresh should add or replace captures for: the current
Designer toolbar, FGS 1.1 logo and Footer controls, and About dialog;
title-assisted game association; a game page
with an associated GameSheet preview; the LiveSheets list; session setup; and an
active single-scorer or individual-scoring sheet. It should also recapture desktop
and mobile navigation because the conditional LiveSheets link is new.

## Browser tooling and sandbox limitations

The working September 2026 route was the Codex in-app browser's documented
`tab.screenshot({fullPage: true})` API, accessed through the CUA tool. Section
captures used the documented `clip` option, followed by inspection of the saved
file; changing clip width can change the captured layout, so preserve page width.
Use the currently installed browser documentation, not a hard-coded plugin-version
path or an old task's browser/tab IDs.

Screenshot bytes were saved to a temporary PNG, then copied into `docs/images`
through the authorized filesystem tool. The browser runtime did not inherit the
repository write grant. No sandbox policy or browser internals were changed.
The returned bytes were JPEG-encoded despite the chosen filename; convert them
to actual PNG (for example with macOS `sips -s format png`) before copying the
final assets. The documentation test checks file encoding as well as readability.

Standalone Playwright Chromium failed to launch in this Mac agent sandbox with
`bootstrap_check_in ... Permission denied (1100)`. Network/file grants alone did
not resolve that process restriction. Do not retry it indefinitely, disable
sandbox protections, or access private browser transports as a workaround.

On September 14, 2026, the in-app browser successfully rendered the disposable
Metadata portability page in one hidden tab, but its current screenshot method
returned only the visible viewport even when full-page capture was requested.
The returned image could be inspected in conversation but was not exposed as a
local file suitable for repository verification. Do not create repeated tabs or
empty windows in response. Keep one hidden tab, verify the accessibility tree
and viewport, and defer the repository image until the supported browser API can
produce a complete local artifact.

A future repository-owned Playwright capture job on an authorized local runner
or GitHub Actions would reduce dependency on interactive tooling. That job is
**not implemented** by this documentation refresh. Pin the browser/environment
and use the same synthetic fixture if it is added; images still need human review.

## Refresh verification — September 13, 2026

- All ten README gallery images inspected. The two current Sheet Designer images
  replace the stale navigation-only captures in the public gallery.
- Documentation and Sheet Designer tests: 24 passed. Full Mac suite: 651 passed,
  1 skipped. Ruff and `git diff --check`: passed.
- Only disposable fictional library data and example-only URLs were used. No live
  library, real account details, or guest token was captured.

## Metadata portability review — September 14, 2026

- The new page was rendered from current source using a disposable empty library
  and synthetic Admin on loopback.
- Page structure, fonts, spacing, form controls, buttons, and navigation label
  were visually inspected. No existing gallery screenshot became inaccurate.
- A new gallery image was deliberately deferred because only a partial viewport
  could be saved through the available browser path.
