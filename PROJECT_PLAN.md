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
9. **Confirmed:** External enrichment services are outside the MVP. The first
   approved enrichment workstream is the Phase 2 BoardGameGeek integration.
10. **Confirmed:** Work should proceed in small, tested Git commits.
11. **Confirmed:** Forge GameSheets remains useful from locally cached state
    when optional external services are unavailable.
12. **Confirmed:** Security is a primary release requirement. Perform an
    evidence-based OWASP ASVS self-assessment as a future action and before
    every major release; remind the owner to arrange an independent review
    at those checkpoints. See [security planning](docs/SECURITY_PLAN.md).

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
- **Confirmed:** Warn that authentication is off until local setup and Forge must not be
  exposed directly to the public Internet.
- **Confirmed:** Retain the application health check and verify that container
  health represents a functioning application rather than merely an existing
  container.
- **Confirmed:** Add focused checks for runtime identity, writable application
  data, read-only source content, and application health.
- **Confirmed:** Add concise setup and security guidance sufficient for current
  testers, including opt-in authentication and the difference
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
- **Confirmed:** Do not pull the Phase 3 FGS schema, editor, renderer, visual
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
  needed before declaring the Phase 1.5 release stable and beginning the BGG
  integration.

## 7. Phase 1.5 — Forge Mark and QR reprints

- **Confirmed roadmap:** Offer optional printable copies with a small Forge Mark,
  brief reprint instructions, and a QR code.
- **Confirmed:** QR destinations open a resource page with view/print actions;
  scanning must not trigger printing automatically.
- **Proposed:** Stable application URLs should survive display-title changes.
- **Future idea:** Configurable branding/footer placement and access policies.

## 8. Phase 2 — BoardGameGeek integration

**On hold:** The BGG application has been submitted. Pause further enrichment
features and public rollout pending approval and guidance on token distribution
for self-hosted installations. Retain the existing optional client, association
storage, matching service, and manual workflow; do not remove stored data or
rewrite migrations. No token is bundled with the application.

Integration housekeeping is implemented: BGG actions are gated by token
configuration, unavailable game-page controls are hidden, and Settings shows
configuration status without claiming approval or verified working access.
FGS planning does not require a BGG ID, but moving into Phase 3 remains an
explicit scope decision rather than an automatic consequence of this pause.

BoardGameGeek (BGG) is the primary approved external reference and enrichment
source. A local Forge game remains the primary object, and normal library use
must not depend on BGG availability after enrichment data has been cached.

- **Confirmed:** Use the official BGG XML API2 where possible. Do not scrape
  BGG HTML or depend on undocumented/private APIs without a later explicit
  decision.
- **Confirmed:** Isolate BGG HTTP, XML parsing, URL generation, caching, and
  failure handling behind a distinct service boundary.
- **Confirmed:** Persist a selected BGG ID and match state with the local game.
  Support matched, unmatched, ambiguous, and manually matched behavior without
  silently accepting uncertain results.
- **Confirmed:** Retain manually resolved associations across scans until the
  user explicitly changes or removes them.
- **Confirmed:** BGG lookup failures, rate limiting, authorization failures, and
  ambiguous results never block local discovery or normal library access.
- **Confirmed:** Cache only useful enrichment metadata, such as the BGG name,
  artwork references, match information, and refresh timestamp; do not clone
  the BGG database.
- **Confirmed:** Preserve local artwork. A reliable BGG image may be used as a
  fallback when local artwork is absent, and users may explicitly choose a BGG
  image later.
- **Confirmed:** Provide game-page and Files-page navigation derived from the
  stored BGG ID, plus manual find, change, unlink, retry, and artwork actions.
- **Confirmed:** BGG lookup is enabled by default for ordinary library entries
  but can be disabled per entry. Preserve a future path-level default with an
  entry-level override; do not model applicability as `is_board_game`.
- **Confirmed:** Store credentials or API configuration only through the
  established application configuration/environment boundary.
- **Confirmed:** The BGG ID is an optional stable external identifier available
  to future FGS files and workflows. It is not required for every Forge game or
  every FGS file.

Before implementation, review the current database, scanner, artwork, settings,
and test architecture; propose the migration, service interface, matching
policy, caching policy, and affected files. Implement the service and mocked
tests before connecting external lookup to scanning.

The complete approved boundary is recorded in
[`docs/decisions/003-boardgamegeek-integration.md`](docs/decisions/003-boardgamegeek-integration.md).

## 9. Phase 3 — FGS Structured GameSheet System

Forge GameSheets is the application. **FGS** is its portable structured
GameSheet format, and `.fgs` is the native extension. An FGS file is editable
source; a **GameSheet** is a rendered result.

- **Confirmed:** FGS is a human-readable, plain-text, declarative, versioned
  format. YAML is the preferred representation unless schema design finds a
  compelling reason to use another structured text format.
- **Confirmed:** Design and document the formal FGS v1 schema before building
  the editor or renderer. Illustrative YAML in planning documents is not the
  final schema.
- **Confirmed:** FGS describes semantic document structure rather than fixed
  PDF coordinates wherever practical.
- **Confirmed:** Support reference sheets, record/score sheets, and hybrid
  sheets across board games, RPGs, miniatures, card games, yard games, sports,
  tournaments, and other competitions. Do not hardcode the format around one
  game category or document type.
- **Confirmed:** Plan for headings, text, images, tables, grids, writable
  fields, checkboxes, repeated structures, calculations, QR codes, page breaks,
  and multi-page output without requiring all primitives in FGS v1.
- **Confirmed:** An FGS renderer may target PDF, print, browser-rendered views,
  and future outputs. The model must not assume PDF-only or static-only use.
- **Confirmed:** A game may have zero, one, or many independent FGS files.
  Existing PDFs remain static artifacts and are not interchangeable with FGS
  structured sources.
- **Confirmed:** FGS files are portable between installations and must not rely
  on local database IDs or installation-specific filesystem paths.
- **Confirmed:** Imported FGS files are untrusted. Validate schema and version,
  constrain resource references, prevent path traversal and arbitrary
  filesystem access, and never execute embedded code.
- **Confirmed:** BGG association is optional metadata. An FGS without a BGG ID
  is valid.
- **Confirmed:** Future sharing may include both a rendered GameSheet and its
  editable `.fgs` source. Forge distributes tooling, not third-party game
  content, and will not operate a public FGS repository.
- **Confirmed:** Investigate `forgegamesheets` as the canonical BGG Files
  discovery convention. Do not scrape BGG Files or automate uploads without an
  officially supported API and a later explicit decision.

Major future components are the FGS v1 specification, validation, import and
export, storage and game association, FGS Library, FGS Editor, FGS Renderer,
static and browser outputs, version migration, and external community-sharing
navigation. The exact launch subset will be selected after schema design.

Representative user stories include quick references, setup guides, writable
score sheets, resource trackers, character sheets, golf scorecards, tournament
brackets, and hybrid reference/tracking sheets. These examples preserve product
intent; they are not all FGS v1 requirements.

The complete approved boundary is recorded in
[`docs/decisions/002-fgs-format-and-architecture.md`](docs/decisions/002-fgs-format-and-architecture.md).

## 10. Phase 4 — design and advanced workflows

Documentation is release-critical: automated checks run with pytest, and major
updates require critical-path and screenshot review under
[documentation review](docs/DOCUMENTATION_REVIEW.md), alongside security review.

### Approved token-free BGG baseline

Implemented locally: Admin/Contributor full BGG game-URL association (ID and slug required),
canonical Game/Files links, and a title-based external search shortcut for unlinked
games. No scraping or API requests; local title/artwork remain authoritative.
Manual associations disable automatic matching until explicitly enabled. API
enrichment rollout remains separate and subject to approval/token configuration.

### Approved bulk game categorization

Implemented locally, awaiting owner review: Games → Assign game categories for
Admins/Contributors, with title/category filters, newest/title sorting, selection
of up to 500 displayed games, and transactional add/remove/replace/clear actions.
All operations show a pre-apply confirmation summary. Settings → Library scanning provides
an Admin-only, default-off trailing `[Dice, Children]` folder convention for new
games. Existing games require preview and explicit additive application; rescans
preserve manual categories. No filesystem writes or bulk title changes occur.


### Approved early access-control milestone

The owner approved moving the small local-account foundation ahead of PDF
uploads. Implement opt-in local Admin bootstrap/recovery, Admin/Contributor/
Reader permissions, and resource-scoped QR guest access with an Admin-controlled
allow/restrict setting. Existing installations remain in trusted-operator mode
until local setup activates authentication. Once active, library browsing requires
sign-in; existing numeric QR links require sign-in, while explicitly created
secure sharing links may allow guests. Content, shared favorites/pins/history,
and filesystem permissions remain unchanged. No public registration, email
recovery, external identity provider, PDF upload, or deployment is included.
See [the access-control design](docs/decisions/004-local-accounts-and-sharing.md).

- **Implemented locally, awaiting owner review:** The approved local-account
  milestone above, including default-allow secure QR guest policy and optional
  Reader-or-higher sign-in. No live installation has been activated by this work.
  See [account operations](docs/ACCOUNTS.md). Broader identity providers, MFA,
  per-user collections, and PDF uploads still require separate approval.
- **Future consideration, owner approval required:** Web-based creation of
  game entries and single-PDF uploads as a convenience alongside filesystem
  bulk loading. Review security and mount permissions before implementation;
  see [security planning](docs/SECURITY_PLAN.md).
- **Future idea:** Visual FGS designer.
- **Future idea:** Multi-document game-night packs.
- **Future idea:** Advanced layout and print optimization.
- **Future idea:** Additional FGS render targets and interactive workflows.
- **Future idea:** Additional external integrations after BGG is stable.

## 11. Proposed technical baseline

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

## 12. Development and Git strategy

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

## 13. Decisions to preserve

- Do not store source PDFs in SQLite.
- Do not reject resources because filenames are imperfect.
- Do not require sidecar metadata.
- Do not hardcode individual games into application logic.
- Do not let future generation needs distort the Phase 1 scope, but keep the
  resource abstraction compatible with them.
- Do not make normal local library use dependent on BGG availability.
- Do not require a BGG ID for a Forge game or FGS file.
- Do not make FGS executable, PDF-only, tied to internal database IDs, or
  limited to one document per game.
- Do not ship copyrighted third-party game files or community-created FGS
  content with Forge.
- Do not expose arbitrary filesystem paths through the web application.
- Do not begin production deployment until the local milestones are tested and
  production host, port, storage, permissions, backups, and access are reviewed.

## 14. Open questions for incremental validation

- Exact rules for recognizing game folders below the first level.
- Filename precedence and the initial category alias table.
- Whether missing files are immediately removed from the index or retained as
  unavailable for a short diagnostic/history window.
- Thumbnail generation library and cache invalidation strategy.
- Whether print history records an explicit in-app action or only resource use,
  since browser printing cannot always be observed reliably.
- Authentication and network exposure expectations for eventual deployment.
- BGG API authorization requirements, request policy, cache lifetime, and
  confidence thresholds, to be verified against official documentation before
  implementation.
- Formal FGS v1 schema, including semantic content blocks, resource references,
  calculations, layout hints, page behavior, and compatibility rules.

Open questions should be resolved through small implementation experiments and
documented decisions, not broad redesigns.
