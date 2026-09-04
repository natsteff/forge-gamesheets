# README screenshot maintenance

## Current set

Captured September 4, 2026 from application revision `14f76af`, with only pending
documentation edits. The demo uses invented games (Lantern Vale, Pebble Parade,
Pocket Orchard, Starship Signals), original sample PDFs and simple cover art,
and disposable demo accounts. It has no BGG token or real game association.
The build panel correctly says Development build: this was a local source run,
not a published-container verification.

The gallery contains library-overview, game-resources, assign-categories,
forge-reprint, settings, users, bgg-manual, settings-build, desktop-navigation,
and mobile-navigation PNGs in `docs/images/`. The account image focuses on roles
and QR policy; it is not a screenshot of the entire long Users page.

## Repeatable capture checklist

1. Use a disposable demo directory outside the repository, with its own library
   and database. Generate original sample PDFs/artwork; never copy a personal
   library or use live account data. Start the current application on loopback
   with explicit demo library/data paths. Do not load the deployment's `.env`.
2. Bootstrap a disposable Admin and Reader in that demo only. Add a few category
   assignments and pinned resources. Leave all passphrase fields empty in captures.
3. Capture the gallery routes: `/`, `/games/{demo-id}`, `/assign-categories`,
   `/r/{demo-resource-id}`, `/settings`, `/settings/users`, and
   `/games/{demo-id}/edit`. Discover IDs from the demo; do not assume production IDs.
4. On bulk categories, select games and a category to illustrate the controls;
   no change need be applied. Generate an ordinary demo reprint to show its ready
   state. Do not create or expose live guest-sharing links. Leave the BGG input
   empty rather than pretending an invented game has a real BGG listing.
5. Capture the Games dropdown at desktop width and the open hamburger menu at
   390 × 844 for the phone view. Restore any temporary viewport override afterward.
6. Inspect every saved PNG, not just the live browser. Check text, cropping,
   responsive wrapping, loaded fonts/previews, empty password fields, and absence
   of private paths, hostnames, tokens, or real account details. Section crops must
   retain the full explanation and controls. Update captions to match actual content.
7. Replace all affected images together with the README; run documentation tests,
   the full suite, and lint. Review the rendered gallery before publication. Stop
   the temporary server when finished. Do not commit demo databases or PDF files.

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

A future repository-owned Playwright capture job on an authorized local runner
or GitHub Actions would reduce dependency on interactive tooling. That job is
**not implemented** by this documentation refresh. Pin the browser/environment
and use the same synthetic fixture if it is added; images still need human review.

## Refresh verification — September 4, 2026

- All ten saved gallery images inspected; desktop and phone navigation captured.
- Local rendered README gallery reviewed with all ten images loading.
- Documentation tests: 5 passed. Ruff and `git diff --check`: passed.
- Full Mac suite: 586 passed, 1 failed. The existing scanner case-sensitivity
  fixture cannot create distinct `Alpha` and `alpha` directories on this host.
  No scanner code or test was changed as part of this refresh.
- No live library used, no guest token exposed, and no commit or publication made.
