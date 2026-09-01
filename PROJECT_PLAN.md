# Forge GameSheets Project Plan

Status labels used below:

- **Confirmed** — approved planning baseline; do not redesign casually.
- **Proposed** — preferred implementation direction, subject to validation.
- **Future idea** — deliberately outside the current milestone.

## 1. Project identity

- **Confirmed:** Product name: **Forge GameSheets**
- **Confirmed:** Tagline: **Organize. Customize. Print. Play.**
- **Confirmed:** Repository and container naming: `forge-gamesheets`
- **Confirmed:** The product is a self-hosted printable-game-resource library
  and, in later phases, a print-on-demand document forge.
- **Confirmed:** Brand artwork exists outside this repository and will be added
  to `app/static/brand/` when an approved source asset is available.

## 2. Problem and hosting model

Board-game rules, score sheets, quick references, player aids, and other
printables tend to be scattered across folders and websites. Forge GameSheets
will provide one browsable, searchable place to organize and print them.

- **Confirmed:** The application will be self-hosted.
- **Confirmed:** Docker Compose is the target packaging and runtime workflow.
- **Confirmed:** The library, configuration, and application data remain in
  ordinary host directories so they are portable and easy to back up.
- **Confirmed:** Production is expected eventually under
  `/opt/forge-gamesheets/`, but production deployment is not part of repository
  setup or the first development milestone.
- **Confirmed:** No cloud service is required for core operation.

## 3. Design principles

1. **Confirmed:** The filesystem is authoritative for library content.
2. **Confirmed:** SQLite is an index/cache and stores application state; PDF
   blobs do not belong in the database.
3. **Confirmed:** Existing PDFs work without metadata or database entry.
4. **Confirmed:** Naming conventions improve discovery but are not mandatory.
   Unrecognized files remain accessible as `Other` rather than being rejected.
5. **Confirmed:** First-level library directories represent games; PDFs are
   discovered recursively within them.
6. **Confirmed:** The UI must work well on phones, tablets, and desktops.
7. **Confirmed:** Static PDFs and future generated documents are both modeled
   as resources belonging to a game.
8. **Confirmed:** Dynamic document generation is outside Phase 1.
9. **Confirmed:** External enrichment services are outside the MVP.
10. **Confirmed:** Work should proceed in small, tested Git commits.

## 4. Filesystem convention

The expected basic layout is:

```text
library/
├── Yahtzee/
│   ├── Yahtzee - Rules.pdf
│   ├── Yahtzee - Score Sheet.pdf
│   └── Yahtzee - Quick Reference.pdf
└── Farkle/
    ├── Farkle - Rules.pdf
    └── Farkle - Scoring Reference.pdf
```

- **Confirmed:** Folder name supplies the default game name.
- **Confirmed:** Preferred filename shape is
  `<Game Name> - <Document Type> [optional variant].pdf`.
- **Confirmed:** The parser must be tolerant of deviations.
- **Confirmed:** Common aliases normalize to stable categories. Examples:
  `rules`, `score_sheet`, `reference`, `answer_sheet`, `tournament`, `setup`,
  and `other`. Instructions normalize to rules; player aids and cheat sheets
  normalize to player references.
- **Proposed:** Optional `game.yaml` and document sidecars can later provide
  titles, aliases, tags, player counts, paper information, and overrides.
  Sidecars must never be required for basic discovery.

## 5. Resource model

A game owns resources. In Phase 1, the only provider is a discovered PDF. Later
providers may include generated PDFs, HTML references, images, or links.

Minimum Phase 1 concepts:

- Game: stable identity, display title, filesystem path, timestamps.
- Resource: game, provider/type, category, title/variant, source path, file
  identity, timestamps, and availability state.
- Application state: favorite, recent use, print history, and scanner status.

- **Confirmed:** Files removed from the filesystem must not remain falsely
  available after a successful scan.
- **Proposed:** Use stable derived identifiers where possible so rescans preserve
  application state when files are unchanged.
- **Proposed:** Keep scanner, filename parser, persistence, HTTP layer, and UI
  concerns independently testable.

## 6. Phase 1 — PDF library and manager

### Core milestone

- Scan a configured library root.
- Treat each first-level directory as a game.
- Discover PDFs recursively.
- Infer document category and variant from forgiving filenames.
- Persist the current index in SQLite.
- Browse all games and open a game's resources.
- Search games and documents.
- View, download, and use browser printing for PDFs.
- Manually rescan the library and report useful results/errors.
- Provide tests for discovery, parsing, reconciliation, and path safety.

### Phase 1 completion features

- Favorites.
- Recently used resources.
- PDF thumbnails/previews.
- Print/use history.
- Clear empty, unavailable, malformed, and partial-scan states.
- Responsive and accessible navigation.

### Explicitly out of scope for Phase 1

- Editing source PDFs.
- Dynamic score-sheet generation.
- QR stamping or public reprint links.
- Visual template design.
- BoardGameGeek or other external metadata integration.
- User accounts, remote synchronization, or cloud storage.
- Automatic production deployment.

### Phase 1 transition to Phase 1.5 and wider beta

The completed Phase 1 library will receive the small deployment fixes already
identified through real-host testing, then development will move directly into
Phase 1.5. Wider external beta recruitment, the complete setup guide, and the
public screenshot set will follow a demonstrable Phase 1.5 generation workflow
rather than delaying feature progress beforehand.

#### Milestone A — Essential self-hosting fixes

- **Confirmed:** Keep the container process non-root and give its runtime user a
  deterministic, documented numeric UID/GID.
- **Confirmed:** Keep the source PDF library mounted read-only and application
  data in a separate writable persistent host directory.
- **Confirmed:** Preserve localhost-only access as the safe Compose default.
- **Confirmed:** Make the bind address, host port, data path, and library path
  configurable without requiring users to edit tracked Compose configuration.
- **Confirmed:** Clearly distinguish localhost-only, trusted-LAN, and
  reverse-proxy access models.
- **Confirmed:** Warn that Forge has no built-in authentication and must not be
  exposed directly to the public Internet.
- **Confirmed:** Retain the application health check and verify that container
  health represents a functioning application rather than merely an existing
  container.
- **Confirmed:** Add focused checks for runtime identity, writable application
  data, read-only source content, and application health.
- **Confirmed:** Add concise setup and security guidance sufficient for current
  testers, including the lack of built-in authentication and the difference
  between localhost-only and trusted-LAN access.
- **Confirmed:** Do not add a privileged startup process, broad host
  permissions, automatic NAS mounting, bundled TLS, or a larger orchestration
  stack as part of this milestone.

#### Milestone B — Phase 1.5 generated reprint foundation

- **Confirmed:** Introduce generated printable copies as derived resources
  without modifying or replacing the authoritative source PDFs.
- **Confirmed:** Add a small configurable Forge Mark, brief reprint guidance,
  and a QR code to generated copies.
- **Confirmed:** Use stable application resource URLs that survive display-title
  changes.
- **Confirmed:** A QR destination opens a resource page with deliberate view and
  print actions; scanning a code must never trigger printing automatically.
- **Confirmed:** Store generated output and its metadata separately from the
  source library and make its lifecycle and cleanup behavior explicit.
- **Confirmed:** Preserve safe path handling, read-only source mounts, and the
  filesystem-as-source-of-truth rule for original library content.
- **Confirmed:** Add tests for generated-file safety, stable URLs, QR targets,
  and failure behavior before exposing the workflow in the interface.

#### Milestone C — Phase 1.5 user workflow

- **Proposed:** Start with one constrained generated-copy workflow rather than
  a general template designer or game-specific document generator.
- **Proposed:** Let a user choose an existing PDF resource, preview the derived
  copy, and intentionally generate or download it with the Forge Mark and QR
  reprint information.
- **Confirmed:** Make generated and static resources understandable within the
  existing game/resource interface.
- **Confirmed:** Provide clear states for generation in progress, success,
  unsupported input, and failure without damaging the source PDF.
- **Confirmed:** Validate the workflow on representative page sizes and
  multi-page PDFs before expanding its options.
- **Confirmed:** Do not pull the Phase 2 declarative template engine, visual
  designer, or configurable score-sheet generation into this milestone.

#### Milestone D — Deployment documentation and public presentation

- **Confirmed:** Add `docs/deployment.md` as the detailed self-hosted beta guide
  while keeping the README concise.
- **Confirmed:** Document prerequisites, installation location, port selection,
  persistent storage, permissions, access modes, startup, health verification,
  initial library organization, normal management, upgrades, backups, and
  common failures.
- **Confirmed:** Explain that host bind-mount paths may point to local disks or
  storage already mounted by the host operating system, including NAS-backed
  paths; Forge does not mount NFS, SMB, or NAS storage itself.
- **Confirmed:** Include exact troubleshooting guidance for an unwritable data
  directory, an occupied port, localhost-only access, missing library content,
  and a container that exits immediately after creation.
- **Confirmed:** Keep deployment examples suitable for a clean Linux Docker
  host while making clear that example paths such as `/opt/forge-gamesheets`
  are recommendations rather than requirements.
- **Confirmed:** Add a concise screenshot gallery to the README using
  repository-relative image paths.
- **Confirmed:** Include representative views of the library/categories, a
  game's resources, Settings, and the Phase 1.5 generated-copy workflow using
  invented or otherwise safe sample data.
- **Confirmed:** Remove personal paths, hostnames, bookmarks, copyrighted PDF
  contents, and other private details from public screenshots.
- **Confirmed:** Add a dedicated social-preview image sized and compressed for
  GitHub link sharing.
- **Confirmed:** Keep screenshots visually consistent and provide useful alt
  text.

#### Milestone E — Wider external beta launch

- **Confirmed:** Run the full automated test and lint suite, then complete a
  clean-host deployment walkthrough in both localhost-only and trusted-LAN
  modes.
- **Confirmed:** Verify install, health, first scan, restart, backup, and update
  instructions against the release candidate.
- **Confirmed:** Publish a new prerelease rather than moving or rewriting the
  existing `v0.1.0-beta.1` tag.
- **Proposed:** Select the next prerelease version after the Phase 1.5 work is
  complete rather than reserving `v0.1.0-beta.2` prematurely.
- **Confirmed:** Provide beta testers with a short testing guide, known
  limitations, security warning, and an obvious way to report defects.

#### Milestone F — External beta feedback triage

- **Confirmed:** Classify reports as setup/documentation, defect, usability,
  compatibility, security, or later-phase enhancement.
- **Confirmed:** Prioritize data safety, path safety, failed startup, broken
  upgrades, and inaccessible documents ahead of cosmetic improvements.
- **Confirmed:** Keep fixes small and tested; do not expand beyond the approved
  Phase 1.5 workflow or pull Phase 2 features into beta stabilization.
- **Proposed:** Use the external beta results to decide whether another beta is
  needed before declaring the Phase 1.5 release stable and beginning Phase 2
  planning.

## 7. Phase 1.5 — Forge Mark and QR reprints

- **Confirmed roadmap:** Offer optional printable copies with a small Forge Mark,
  brief reprint instructions, and a QR code.
- **Confirmed:** QR destinations open a resource page with view/print actions;
  scanning must not trigger printing automatically.
- **Proposed:** Stable application URLs should survive display-title changes.
- **Future idea:** Configurable branding/footer placement and access policies.

## 8. Phase 2 — declarative print-on-demand generation

Phase 2 introduces configurable templates as another resource provider rather
than replacing the Phase 1 library.

- **Confirmed:** Templates describe documents declaratively; do not hardcode a
  separate renderer for every game.
- **Confirmed:** Generic primitives and a layout engine handle tables, text,
  scoring rows, repeated cards, margins, orientation, and pagination.
- **Confirmed:** Preserve the lifecycle:
  template → saved configuration → immutable print snapshot.
- **Confirmed:** Layout supports full sheet (1 item), half sheet (2 items), and
  quarter sheet (4 items), with templates able to restrict unreadable sizes.
- **Confirmed:** Generated and static resources coexist in the same game view.

Representative user stories include configurable Yacht-style score sheets,
Farkle round sheets, Bunco packs, Euchre tournament assignments, randomized
Bingo cards, and tasting/judging sheets. These examples preserve product intent;
they are not all Phase 2 launch requirements.

## 9. Phase 3 — design and advanced workflows

- **Future idea:** Visual template designer.
- **Future idea:** Multi-document game-night packs.
- **Future idea:** Advanced layout and print optimization.
- **Future idea:** Template import, export, and sharing.
- **Future idea:** Optional external library enrichment.

## 10. Proposed technical baseline

- Python web application using FastAPI.
- Server-rendered responsive interface initially; avoid an unnecessary separate
  frontend build until product needs justify it.
- SQLite for index/cache and application state.
- SQL migrations from the first persisted schema.
- Filesystem adapters for library discovery and safe PDF delivery.
- Pytest for unit and integration tests.
- Ruff for formatting and linting; type checking can be added when the initial
  code shape is established.
- Docker image and `compose.yml` for reproducible development and later hosting.

These are proposed implementation choices, not permission to expand Phase 1.

## 11. Development and Git strategy

- Keep `main` in a runnable, tested state.
- Make one focused change per commit; include tests with the behavior they cover.
- Prefer vertical milestones that can be demonstrated locally.
- Record meaningful architecture decisions under `docs/decisions/`.
- Never commit real personal library PDFs, local databases, secrets, or generated
  runtime data.

Suggested early commits after this scaffold:

1. Minimal FastAPI health endpoint and test.
2. Library configuration and path validation.
3. Filesystem scanner with fixture-based tests.
4. Forgiving filename/category parser with table-driven tests.
5. SQLite schema, migrations, and scan reconciliation.
6. Read-only library and game views.
7. Safe PDF view/download behavior.
8. Search and manual rescan.

## 12. Decisions to preserve

- Do not store source PDFs in SQLite.
- Do not reject resources because filenames are imperfect.
- Do not require sidecar metadata.
- Do not hardcode individual games into application logic.
- Do not let future generation needs distort the Phase 1 scope, but keep the
  resource abstraction compatible with them.
- Do not expose arbitrary filesystem paths through the web application.
- Do not begin production deployment until the local milestones are tested and
  production host, port, storage, permissions, backups, and access are reviewed.

## 13. Open questions for incremental validation

- Exact rules for recognizing game folders below the first level.
- Filename precedence and the initial category alias table.
- Whether missing files are immediately removed from the index or retained as
  unavailable for a short diagnostic/history window.
- Thumbnail generation library and cache invalidation strategy.
- Whether print history records an explicit in-app action or only resource use,
  since browser printing cannot always be observed reliably.
- Authentication and network exposure expectations for eventual deployment.

Open questions should be resolved through small implementation experiments and
documented decisions, not broad redesigns.
