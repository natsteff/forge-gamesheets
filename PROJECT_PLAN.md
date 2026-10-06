# FORGE GameSheets Project Plan

Status labels used below:

- **Confirmed** — approved planning baseline; do not redesign casually.
- **Proposed** — preferred implementation direction, subject to validation.
- **Future idea** — deliberately outside the current milestone.

## 1. Project identity

- **Confirmed:** Product name: **FORGE GameSheets**
- **Confirmed:** Tagline: **Collect. Create. Print. Play. Or Go Live with LiveSheets.**
- **Confirmed:** Repository and container naming: `forge-gamesheets`
- **Confirmed:** The product combines a self-hosted GameSheet designer,
  temporary LiveSheet scoring, and a printable-game-resource library with PDF
  management.
- **Confirmed:** Brand artwork exists outside this repository and will be added
  to `app/static/brand/` when an approved source asset is available.

## 2. Problem and hosting model

Board-game rules, score sheets, quick references, player aids, and other
printables tend to be scattered across folders and websites. FORGE GameSheets
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
11. **Confirmed:** FORGE GameSheets remains useful from locally cached state
    when optional external services are unavailable.
12. **Confirmed:** Security is a primary release requirement. Perform an
    evidence-based OWASP ASVS self-assessment as a future action and before
    every major release. Automated checks and maintainer-led, AI-assisted review
    are the planned release controls; do not claim independent certification.
    See [security planning](docs/SECURITY_PLAN.md).
13. **Confirmed:** New FORGE GameSheets releases use `AGPL-3.0-only` to keep
    distributed forks and modified network deployments source-available.
    Versions through commit `91ba590` were offered under MIT and retain those
    historical terms. The software license does not apply to user-managed PDFs,
    artwork, FGS documents, metadata, or databases. See
    [licensing guidance](docs/LICENSING.md).

### Current execution sequence

Owner-approved separate increment — manual BGG edition reference on FORGE GameSheets game
entries: optional version URL or ID and readable label in the existing BGG editor
section, token-free Versions shortcut and View your edition action. Implemented
and owner-reviewed. Migration 32 adds empty optional edition storage; rescans
and metadata export/import preserve the reference independently of dimensions.
A changed parent association prompts edition review rather than deleting it.
No API verification, BGG dimension import, FGS or rendering changes are included.
Future work: API-backed edition selection and explicit dimension retrieval.
Local follow-up: API-created/refresh associations capture the canonical game slug
from a bounded, unauthenticated public redirect inspection. Older entries can be
repaired through an explicit token-free editor action. Files/Versions shortcuts
require the slug; otherwise show main-page fallbacks. Edition main-page URLs stay
ID-only, relying on BGG's version-page redirect. No automatic page-view/scanning
requests, scraping, game-ID replacement or measurement changes are introduced.

Owner-approved separate increment — optional physical box dimensions on FORGE GameSheets
game entries only: manual Length/Width/Depth plus explicit in/cm unit, existing
edit/detail UI, application-data persistence and metadata export/import.
Implemented and owner-reviewed. Legacy records remain unknown; migration 31
adds empty optional storage. The associated game's dimensions are shown as a
reference in the Designer header. No BGG retrieval, FGS specification,
renderer, PDF or fit-to-box changes are part of this increment.

Owner-approved implementation — trackers and music / reusable paper in FORGE GameSheets
and FGS Studio, including basic host-controlled shared LiveSheet trackers.
FGS 1.3 and Page Rendering Profile 1.3 are implemented and owner-reviewed. See the
[1.3 specification](docs/FGS_V1_3_SPECIFICATION.md) and
[rendering profile](docs/FGS_PAGE_RENDERING_PROFILE_1_3.md).
New sections cover bounded trackers, ruled/square/dot/hex paper, single/paired
music staves and tablature, with fixed sizing or one final full-width fill section.
Owner-approved additions: coordinate grids with axes,
and single/repeated blank tic-tac-toe, Dots and Boxes and Sudoku boards. No puzzle
generation, solving or interactive board gameplay is included.
Automated tests and visual PDF review passed; the owner confirmed browser
PDF download and FGS download/re-import in Studio. Commit/push approval was
given. The publication process must verify both container variants and the
hosted Studio after their GitHub Actions workflows complete. See the
[development review](docs/FGS_1_3_LOCAL_REVIEW.md) for local verification evidence.
Personal health measurement logs, multipage output, MusicXML import, general
tables/fields and advanced freeform layouts remain separate future work.

Completed and published — global Links (owner accepted the installed update):
FORGE GameSheets only, with
one Links page showing Personal Favorites for signed-in users above Admin-curated
FGS Favorites, followed by enabled links grouped by editable categories.
Admin manages links and FGS Favorites on the same Links page; personal
favorites reference existing enabled links only.
The unified directory uses compact resource-style rows, alphabetical within
each category, with an Admin toolbar and collapsed grouped disabled entries.
Category editing remains a separate Admin tool; category and shared-favorite
order stay configurable, but per-link directory order is no longer editable.
Rows have
personal stars and Admin-only pins (shared FGS Favorites), edit and confirmed
delete controls; favorite shortcut sections remain unchanged. Deletion uses a
focused confirmation page with Cancel. New categories default to the next order
after the existing maximum, within the supported limit.
The original Links release seeded three categories and fourteen starter links,
with FGS Favorites initially empty. Upgrades preserve edits and deletions;
explicit Add missing starter links restores missing defaults without
overwriting records.
The current bundled file adds a fifteenth, separately identified FORGE TTRPG
web link and a sixteenth FGS Studio link. Both are shared Favorites by default
for new or explicitly restored entries. Existing installations add missing
links only through the explicit starter-link action; the original seed history
is unchanged.
Local follow-up: the starter-links toolbar action opens a focused
confirmation page with Add and Cancel, rather than jumping to a collapsed
section; no redundant checkbox is required. Preserve existing game
links, QR guest scope, Designer-only mode and FGS Studio. No scraping, proxying,
mirroring, automatic URL checks or redistribution of third-party content.

Completed and published — multi-architecture container release:
`linux/amd64` and `linux/arm64` are published together under the existing image tags.
Build each runtime variant once, smoke-test and scan both before registry login,
and assemble the release manifest from those exact verified images. Keep Compose
architecture-neutral so Docker selects the native variant automatically. Local
ARM64 builds or emulation alone are not evidence of published ARM64 support.
Publishing CI passed and both registry manifest digests were verified for FORGE GameSheets
revision `e9dde6d`. The owner accepted the installed update. This does not claim
an exhaustive native-ARM64 test matrix or authorize production deployment.

Completed and published — Designer increment (FGS 1.2):
document-level Designer Notes excluded from sheet/PDF/LiveSheet presentation;
optional score-table first-column heading defaulting to Category across both
editors, shared preview/PDF, and LiveSheet; rename the score-table Heading UI
label to Score table title. Preserve 1.0/1.1 compatibility, keep both products
pinned to the same Page Rendering Profile 1.2 build, and do not include unrelated
Designer improvements in this increment.

Publication evidence: FORGE GameSheets source/container revision `e9dde6d`; FGS Studio
revision `0b2ac6f`, automatically deployed to GitHub Pages and verified live.
The release passed FORGE GameSheets’ automated regression/lint, Studio and shared-renderer
tests, dependency audits, and both architecture smoke/scan gates. Existing
accepted Debian High findings remain documented in the security plan; publication
does not claim a vulnerability-free release.

Remaining release work is distinct from completed feature work:

The moving GitHub `main` image is identified as a beta build. This label does
not create a fixed, versioned prerelease or waive the wider-release checks.

**Owner-approved order before the wider, fixed beta prerelease:**

1. Improve BGG enrichment: retrieve fallback cover artwork, description and
   publication year; match exact BGG Category and Mechanism labels to existing
   local categories. Do not use BGG Type or store player count. Newly scanned
   games may gain matching categories only when uncategorized; later scans leave
   categories alone. Admin refresh is additive. After an explicit BGG version
   URL/ID is entered, fill blank edition label and complete blank dimensions
   when the approved API supplies them. Preserve local artwork, manual metadata,
   and explicit category choices; remote failures never block local use.
2. Revisit LiveSheets on mobile. Investigate and fix the current resizing,
   zooming, scrolling, and interaction problems, then validate usability on real
   mobile devices as well as automated viewport tests.
3. After those features stabilize, review and streamline the README, current
   guides, FGS specifications, screenshots, and release documentation. Develop
   a GitHub Wiki overview/getting-started path that links to detailed guides
   instead of duplicating them.
4. Finally, perform the full release-focused security review of the resulting
   candidate under `docs/SECURITY_PLAN.md`, including the maintainer-led,
   AI-assisted OWASP ASVS assessment, dependency/container findings, remediation,
   and explicit treatment of remaining risks before release approval.

These are the owner's current pre-beta priorities, not permission to implement
later-phase features beyond this scope. The existing clean-install,
backup/restore, upgrade, Studio browser-export, offline-BGG, and versioned-release
checks still apply before the wider prerelease.

- **Deferred until the documentation pass above:** Refresh screenshots for
  recent features.
- **Future testing:** No-internet resilience, including graceful BGG failure.
- **Outstanding verification:** An actual browser-driven Studio PDF download
  check; automated shared preview/PDF tests have passed.
- **Before a wider versioned prerelease:** Clean-install, backup/restore and
  upgrade walkthrough, full release security review, release notes/tester guide.
  Do not repeat already completed owner checks merely to advance another feature.

This is the authoritative near-term order. Detailed owner testing may identify
focused corrections, but completed milestones are not repeated merely as gates
for the next approved feature.

1. **Completed:** Phase 1 library, Phase 1.5 individual FORGE GameSheets Reprints, bulk
   game categorization and optional folder-category import, token-free manual
   BGG links, local accounts/resource-scoped QR access, and the initial container
   deployment.
2. **Completed:** Basic owner validation of the updated navigation,
   categorization workflow, account activation, reverse-proxy HTTPS access,
   and Docker upgrade path. Further exploratory testing remains welcome and
   may produce focused follow-up fixes.
3. **Completed:** Keep account activation, Nginx Proxy
   Manager, upgrade, category-hint, screenshot, and security guidance aligned
   with the shipped behavior.
4. **Completed and published:** The Admin-only bulk FORGE GameSheets
   Reprint maintenance utility defined in Milestone D and
   [decision 005](docs/decisions/005-bulk-forge-reprint-maintenance.md).
5. **Completed:** Validate regeneration after application generator changes and
   public/base-URL changes, including preservation of active sharing behavior.
6. **Completed for the published update:** Automated release regression,
   dependency/container gates and owner validation. Deferred screenshots and
   outstanding broader release verification are listed separately above.
7. **Future wider release:** Complete the owner-approved BGG and mobile
   LiveSheets work above, finish the wider-release checklist, select and
   publish a versioned prerelease, then triage external beta feedback.
8. **Completed:** Establish the application-independent FGS v1 specification,
   compatibility policy, schema, prototype migration, and initial conformance
   fixtures before expanding the Designer. See
   [the FGS v1 draft](docs/FGS_V1_SPECIFICATION.md).
9. **Completed:** Support `FORGE_GAMESHEETS_MODE=full|designer` in the same image.
   An omitted value remains `full`, preserving existing installs. Designer mode
   must not initialize the library, scanner, main database, accounts, or
   reprints. Defer separate desktop-editor choices until FGS v1 is stable.

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

A game owns resources. Phase 1 began with discovered PDFs. The later approved
library extension indexes FGS sources, common images and downloadable documents
as categorized resources. Unhandled file types are listed without actions at
the bottom of each game page. PDF-specific previews and Reprints remain PDF-only;
image files have their own browser preview, and importing an FGS creates an
independent Designer copy. Future providers may include HTML references or links.

Minimum Phase 1 concepts:

- Game: stable identity, display title, filesystem path, timestamps.
- Resource: game, provider/type, category, title/variant, source path, file
  identity, timestamps, and availability state.
- Application state: favorites, recent use, paginated activity history, and
  scanner status. Activity includes one aggregate entry for every scan plus
  selected manual content changes and successful PDF use.

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
- **Confirmed:** Warn that authentication is off until local setup and FORGE GameSheets must not be
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
- **Confirmed:** Add a small configurable FORGE GameSheets Mark, brief reprint guidance,
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
  copy, and intentionally generate or download it with the FORGE GameSheets Mark and QR
  reprint information.
- **Confirmed:** Make generated and static resources understandable within the
  existing game/resource interface.
- **Confirmed:** Provide clear states for generation in progress, success,
  unsupported input, and failure without damaging the source PDF.
- **Confirmed:** Validate the workflow on representative page sizes and
  multi-page PDFs before expanding its options.
- **Confirmed:** Do not pull the Phase 3 FGS schema, editor, renderer, visual
  designer, or configurable score-sheet generation into this milestone.

#### Delivered supporting workflows

- **Completed and published:** Games → Assign game categories lets Admins and
  Contributors filter, sort, select, and transactionally add, remove, replace,
  or clear categories for up to 500 displayed games, with a confirmation
  summary before changes are applied.
- **Completed and published:** Admins may optionally import trailing folder
  hints such as `[Dice, Children]` for newly discovered games. Existing games
  require preview and explicit additive application; source folders and files
  are never renamed.
- **Completed and published:** Admins and Contributors may associate a complete
  BGG game URL containing both numeric ID and slug, use canonical Game/Files
  links, or open a title-based BGG search. This baseline makes no API request
  and remains separate from later token-backed enrichment.
- **Completed and published:** Opt-in local Admin/Contributor/Reader accounts,
  recovery, security events, and resource-scoped QR access that is public by
  default and individually restrictable to signed-in users.
  Existing installations remain open until local Admin setup activates access
  control. See [account operations](docs/ACCOUNTS.md) and
  [the access-control design](docs/decisions/004-local-accounts-and-sharing.md).
- **Completed locally:** Admin metadata portability exports uploaded artwork and
  a versioned metadata manifest with Windows and macOS shortcuts, restores
  represented
  metadata with explicit fill-empty or replace policies, and offers a secondary
  read-only shortcut scan.

#### Milestone D — Bulk FORGE GameSheets Reprint maintenance

**Implemented, published, and owner-validated.**

- **Confirmed:** Provide an Admin-only Settings utility with three explicit
  operations: create missing reprints, refresh existing reprints, and create or
  refresh every eligible reprint.
- **Confirmed:** Show inventory and confirmation counts before starting,
  including replacements, new files, skips, and the fact that originals remain
  untouched.
- **Confirmed:** Every generated copy retains its resource's stable QR address.
  Per-resource access changes are enforced when that address is opened and do
  not require regenerating the PDF.
- **Confirmed:** Process the work as a durable background job rather than one
  proxy-sensitive HTTP request. Show persistent progress and per-resource
  failures, allow safe cancellation after the current file, and define recovery
  after container interruption.
- **Confirmed:** Reuse existing rendering locks and file/page/output/free-space/
  derived-storage limits. Process resources sequentially and isolate failures
  so one bad PDF does not abort the full batch.
- **Completed and published:** Persist validation facts for generated reprints so the
  inventory page does not reopen and traverse every PDF on each visit. Existing
  copies are verified and registered once after upgrade.
- **Confirmed:** Centralize individual and bulk QR-target selection in one
  service so both paths enforce identical sharing behavior.
- **Confirmed:** Add migrations, service/route/UI tests, interruption and
  cancellation tests, documentation, backup implications, and security review.
- **Confirmed:** The detailed implementation baseline and remaining engineering
  choices are retained in
  [decision 005](docs/decisions/005-bulk-forge-reprint-maintenance.md).

#### Milestone E — Deployment documentation and public presentation

- **Confirmed:** Add `docs/deployment.md` as the detailed self-hosted beta guide
  while keeping the README concise.
- **Confirmed:** Document prerequisites, installation location, port selection,
  persistent storage, permissions, access modes, startup, health verification,
  initial library organization, normal management, upgrades, backups, and
  common failures.
- **Confirmed:** Explain that host bind-mount paths may point to local disks or
  storage already mounted by the host operating system, including NAS-backed
  paths; FORGE GameSheets does not mount NFS, SMB, or NAS storage itself.
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

#### Milestone F — Wider external beta launch

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

#### Milestone G — External beta feedback triage

- **Confirmed:** Classify reports as setup/documentation, defect, usability,
  compatibility, security, or later-phase enhancement.
- **Confirmed:** Prioritize data safety, path safety, failed startup, broken
  upgrades, and inaccessible documents ahead of cosmetic improvements.
- **Confirmed:** Keep fixes small and tested; do not expand beyond the
  owner-approved pre-beta BGG enrichment and mobile LiveSheets work above or
  pull other later-phase features into beta stabilization.
- **Proposed:** Use the external beta results to decide whether another beta is
  needed before declaring the release stable. Initial BGG integration is already
  complete; the owner-approved enrichment increment above precedes this beta.

## 7. Phase 1.5 — FORGE GameSheets Mark and QR reprints

- **Completed:** Offer optional printable copies with a small FORGE GameSheets Mark,
  brief reprint instructions, and a QR code.
- **Completed:** QR destinations open a resource page with view/print actions;
  scanning must not trigger printing automatically.
- **Completed:** Stable application URLs survive display-title changes.
- **Completed and published:** Bulk maintenance follows
  Milestone D without changing the source-PDF or QR-access boundaries.
- **Future idea:** Configurable branding/footer placement and access policies.

## 8. Phase 2 — BoardGameGeek integration

**Completed — owner accepted live integration validation:** BGG approved FORGE GameSheets as a
non-commercial public-facing XML API application on 2026-09-14. Each independent
self-hosted operator supplies a separately approved token; no token is bundled
with the source or container image. Preserve token-free operation as the default
and retain each operator's responsibility for their API access. Required Powered
by BGG attribution is implemented with BGG's
provided artwork.

Integration housekeeping is implemented: BGG actions are gated by token
configuration, unavailable game-page controls are hidden, and Settings shows
configuration status without claiming approval or verified working access.
FGS documents do not require a BGG ID.

**Current owner-approved pre-beta increment:** Extend the existing BGG integration
with description, publication year and cover fallback; add exact existing-name
matching against BGG Category and Mechanism, never Type. Provide the agreed
33 new-install category defaults while leaving existing installations intact
unless an Admin explicitly adds missing defaults. Initial scan enrichment only
categorizes an uncategorized game; an Admin refresh is additive. Explicitly
selected BGG version URLs/IDs may fill blank label and box dimensions from the
approved API, never overwrite existing values, and work manually without a token.
Do not add player counts or a version picklist. Pace durable batch processing,
make failures visible, and keep local use independent of BGG availability.

**Offline resilience check before the wider prerelease, not a blocker for
implementing enrichment:** The owner has not manually verified FORGE GameSheets
with BGG unavailable. Test the existing installation
with outbound internet access disconnected (while retaining local access) and
confirm local library browsing, existing PDFs, Designer/PDF export and cached
metadata remain usable. BGG-dependent actions should fail gracefully. Record
the result rather than claiming an already verified offline guarantee.

BoardGameGeek (BGG) is the primary approved external reference and enrichment
source. A local FORGE GameSheets game remains the primary object, and normal library use
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
- **Confirmed:** Every independent self-hosted operator is responsible for BGG
  registration and a private token. Ordinary users of that server do not supply
  tokens. Never distribute the project owner's token in source or images.
- **Confirmed:** The BGG ID is an optional stable external identifier available
  to future FGS files and workflows. It is not required for every FORGE GameSheets game or
  every FGS file.

For future BGG changes, preserve the established database, scanner, artwork,
settings and service boundaries; update mocked regression tests before expanding
live integration behavior. Initial integration is no longer a pending milestone.

The complete approved boundary is recorded in
[`docs/decisions/003-boardgamegeek-integration.md`](docs/decisions/003-boardgamegeek-integration.md).

## 9. Phase 3 — FGS Structured GameSheet System

FORGE GameSheets is the application. **FGS** is its portable structured
GameSheet format, and `.fgs` is the native extension. An FGS file is editable
source; a **GameSheet** is a rendered result.

- **Confirmed:** FGS is a human-readable, plain-text, declarative, versioned
  format. FGS v1 uses UTF-8 JSON for browser/Python portability, deterministic
  export, strict parsing, and standard JSON Schema validation.
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
  editable `.fgs` source. FORGE GameSheets distributes tooling, not third-party game
  content, and will not operate a public FGS repository.
- **Completed:** Opening Sheet Designer leads to a lightweight shared-workspace
  choice rather than automatically reopening the last active draft. It offers
  **New sheet**, **Open sheets** (including FGS import), and an explicit
  **Resume last sheet** action. Selecting a sheet opens its editor, where
  automatic saving continues.
- **Completed:** A saved Designer workspace may be associated with one existing
  indexed game without placing installation-specific IDs in its portable FGS
  source. Contributors can search, replace, or remove the association in the
  Designer; associated sheets appear on the game entry with edit and eligible
  LiveSheet launch actions. The relation follows the game folder identity,
  survives display-title changes, and is included with application-data backups.
- **Confirmed:** Investigate `forgegamesheets` as the canonical BGG Files
  discovery convention. Do not scrape BGG Files or automate uploads without an
  officially supported API and a later explicit decision.
- **Completed:** FGS LiveSheet v1 uses temporary,
  permission-scoped sessions. The accepted lifecycle, scoring rules, role
  boundaries, invitation model, and implementation sequence are recorded in
  [decision 006](docs/decisions/006-fgs-livesheet-v1.md). The persistence,
  authorization, calculated-row, and reusable-readiness foundations are
  complete. Conditional navigation, ready-sheet selection, session setup,
  QR/link invitations, player claiming, single-scorer and individual score
  entry, automatic refresh, explicit ending, host-only checklist/game-note
  controls, and the initial visual refinement are implemented.

The visual Designer, independent browser-based FGS Studio, shared preview/PDF
renderer, header logos/footer, FGS 1.2 editorial notes and configurable table
headings are implemented. Global external-resource navigation is provided by Links.
These are not future-work items.

The first small-format print increment is implemented in FORGE GameSheets’ Sheet Designer
and Studio. The reviewed beta keeps Full Page's existing single-page
renderer unchanged while composing Half Page, Poker Card, Bridge Card, and Custom
Size as intentionally designed, single-item sheets. Compact content wraps and
uniformly fits when needed; fit percentage and effective body type size are
reported for the designer to judge, with no hard readability threshold. A
separate Letter/A4 copy-layout export includes an arranged-page preview, cut
guides, Auto or explicit printer-sheet orientation, and explicit borderless two-up Half Page.
FGS 1.4 stores optional finished-size defaults and last-used print-sheet settings
after successful export. Printer paper inherits the design page unless overridden.
The choices remain editable;
the printer-sheet arrangement is still validated at export time.
Opt-in multi-page continuation for Full Page is a separate future milestone;
compact sheets remain one finished item, never automatically another card.

Remaining future components include richer section types beyond the supported
headers, score tables, references, checklists and lined notes; multi-page output;
advanced layout; optional desktop/offline editor packaging; additional render
targets; migrations for future format versions beyond the supported 1.0–1.4;
and any structured community-sharing workflow beyond ordinary external links.
These require their own scope decisions, not automatic implementation.

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

- **Future idea:** Broader identity providers and per-user collections.
- **Not planned:** MFA for the supported localhost, trusted-LAN or protected
  proxy/VPN deployment. Reconsider only if the intended exposure changes.
- **Future consideration, owner approval required:** Web-based creation of
  game entries and single-PDF uploads as a convenience alongside filesystem
  bulk loading. Review security and mount permissions before implementation;
  see [security planning](docs/SECURITY_PLAN.md).
- **Future idea:** Add a read-only **Unsorted documents** presentation that can
  identify and filter resources from a configurable staging folder while
  leaving it as an ordinary first-level game folder on disk. Do not reserve the
  literal `Unsorted` name, move source files, or require a writable library as
  part of this work.
- **Future idea:** Multi-document game-night packs.
- **Future idea:** Advanced layout and print optimization.
- **Future idea:** Additional FGS render targets and interactive workflows.
- **Future idea:** Additional external integrations after BGG is stable.
- **Future release hardening:** When fixed, versioned container releases begin,
  automatically generate an SPDX JSON SBOM from each final runtime image digest
  and attach a signed GitHub/OCI attestation. A plain-text inventory may be
  published as a convenience, but the SPDX document remains authoritative.
  Do not manually maintain or commit generated SBOMs for moving development
  images such as `main`.

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
- Do not require a BGG ID for a FORGE GameSheets game or FGS file.
- Do not make FGS executable, PDF-only, tied to internal database IDs, or
  limited to one document per game.
- Do not ship copyrighted third-party game files or community-created FGS
  content with FORGE GameSheets.
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

Open questions should be resolved through small implementation experiments and
documented decisions, not broad redesigns.
