<p align="center">
  <img
    src="app/static/brand/forge-wordmark.png"
    alt="Forge GameSheets logo"
    width="620"
  >
</p>

# Forge GameSheets

**Organize. Customize. Print. Play.**

Forge GameSheets is a self-hosted manager for PDF-based game resources, including
rulebooks, score sheets, player aids, quick references, and print-and-play
materials. Similar to Plex or Jellyfin for game documents, it scans your existing
folder-based library and turns it into a searchable, browsable collection for
viewing, downloading, and printing.

FORGE GAMESHEETS is in beta, with local library management, optional FORGE
Reprints, and an integrated Sheet Designer for creating new printable game
sheets from scratch. The Designer is a separate creation tool, not an editor
for existing PDFs. Core operation does not modify source PDFs, require a cloud
service, or store PDF contents in its database.

## Available features

- Recursive PDF discovery beneath one first-level folder per game
- Forgiving filename parsing and document-type recognition
- Search across game and resource titles
- Browser viewing, descriptive download filenames, and first-page PDF previews
- Optional FORGE Reprint copies with a QR return link and source-rights notice
- Admin bulk maintenance to create missing, refresh existing, or rebuild all
  eligible FORGE Reprints with durable progress and per-resource results
- Integrated Sheet Designer for creating new structured game sheets from
  scratch, with headers, score tables, references, checklists, notes, live page
  preview, automatically saved drafts, and PDF or `.fgs` export
- Editable display titles, document metadata, and game artwork
- Multiple customizable categories per game
- Bulk category assignment with filtering, selection, and confirmation before changes
- Optional trailing folder-category hints, such as `Yahtzee [Dice, Children]`
- Optional local Admin, Contributor, and Reader accounts with per-resource QR restrictions
- Token-free manual BGG game URLs, Game/Files links, and external title search
- Admin metadata portability for game links and uploaded artwork, with a ZIP
  export, manifest restore, and alternative `.url`/`.webloc` library scan
- All Games, category, and Uncategorized browsing
- Favorites, up to ten pinned homepage resources, Recent, and paginated activity
  history for scans, content changes, and PDF use
- Configurable library footer, Recent limit, and History time zone
- Manual rescans with safe partial-scan and missing-file behavior
- Grouped desktop dropdowns and a compact-screen hamburger menu
- SQLite migrations that preserve application state across restarts
- GitHub-published container images with revision and build-date information

The approved scope and roadmap are in [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Screenshots

Screenshots reviewed September 13, 2026, using an invented demonstration library
and demo accounts. No private library content or third-party game files are
included. These views show authentication enabled; available controls depend on
the signed-in role. Click an image to inspect it at full size.

| Library, pins, and categories | Game resources |
| --- | --- |
| ![Forge GameSheets library showing pinned resources and category cards](docs/images/library-overview.png) | ![An invented game's rules, score sheets, references, and resource actions](docs/images/game-resources.png) |
| **Bulk game categories** | **Bulk FORGE Reprint maintenance** |
| ![Demo games with current categories and bulk assignment controls](docs/images/assign-categories.png) | ![Admin utility showing reprint inventory, guided bulk operations, and recent operation results](docs/images/reprint-maintenance.png) |
| **User Accounts** | **Game Resource Links and BoardGameGeek** |
| ![Admin account controls explaining roles and account management](docs/images/users.png) | ![Game editing with official and alternate resource links and manual BoardGameGeek linking](docs/images/bgg-manual.png) |
| **Activity History** | **Integration and build details** |
| ![Activity history showing summarized scans, content changes, favorites, pins, and PDF use](docs/images/activity-history.png) | ![Settings showing optional integration status and complete local build identification](docs/images/settings-build.png) |
| **Sheet Designer** | **Saved sheets and import** |
| ![Sheet Designer with a compact editing sidebar and live printable-sheet preview](docs/images/sheet-designer.png) | ![Open sheets window with saved drafts, duplication, deletion, and FGS import](docs/images/sheet-designer-open.png) |

The [screenshot maintenance guide](docs/SCREENSHOTS.md) records the capture
procedure and review requirements. The Sheet Designer views also show its new
top-level navigation placement. Older navigation-only captures are temporarily
omitted because they predate that change.

## Requirements

Published images only receive source changes after the corresponding commit
passes the publication checks.

- Docker Desktop or another Docker installation with Compose support
- A local directory containing the PDF library
- A separate writable directory for Forge GameSheets application data

The included `compose.yml` uses the repository's `library/` and `data/`
directories and binds the application only to `127.0.0.1:8000`.

For a persistent Docker-host installation, access-model guidance, upgrades,
backups, and troubleshooting, follow the
[self-hosted beta deployment guide](docs/deployment.md).

## Quick start

Run these commands on the Docker host where FORGE will run. Obtain the
repository once to get `compose.yml` and the example configuration:

```sh
git clone https://github.com/natsteff/forge-gamesheets.git
cd forge-gamesheets
cp .env.example .env
mkdir -p data library
```

Keep host-specific configuration in `.env`, not `compose.yml`. On Linux,
make `data/` writable by the container's `10001:10001` account before starting;
see the [deployment guide](docs/deployment.md). Docker Desktop usually handles
this through file sharing.

1. Put game folders inside `library/`, optionally including local game artwork:

   ```text
   library/
   ├── Farkle/
   │   ├── Farkle - Rules.pdf
   │   ├── Farkle - Score Sheet.pdf
   │   └── icon.png
   └── Yahtzee/
       ├── Yahtzee - Score Sheet.pdf
       └── cover.jpg
   ```

   Images are optional: use `icon` or `cover` with a PNG, JPEG, or WebP
   extension in the game folder. You can also upload artwork later through
   **Edit game entry**. No game PDFs or artwork are bundled with FORGE.

   Optional category hints go at the end of the **game folder name**:
   `Yahtzee [Dice]`, `Yahtzee [Dice, Children]`, or
   `Yahtzee (Family Favorite) [Dice, Children]`. Commas separate categories;
   parentheses remain part of the game title. Missing categories are created
   when hints are applied. PDF filenames do not need the category suffix.

2. Pull the prebuilt image from GitHub Container Registry and start it:

   ```sh
   docker compose pull
   docker compose up -d
   ```

3. Open <http://localhost:8000> on that host. For another device on your trusted
   LAN, configure the bind address and host URL as described below.

   Category import is **off by default**. To use hints for future imports, enable
   **Settings → Library scanning → Import game categories from folder names**
   before adding new game folders, then select **Rescan library**. With accounts
   enabled, this setting requires an Admin.

   Games already discovered on the first startup are not retroactively changed
   by enabling the setting. Use **Games → Assign game categories**, check
   **Preview categories from folder names**, select **Show games**, then select
   the games and apply the folder hints after reviewing the confirmation.
   This adds categories without changing existing titles or removing manual
   assignments. See [game category guidance](docs/GAME_CATEGORIES.md).

4. Stop the application when needed with `docker compose down`.

The health endpoint is available at <http://localhost:8000/health>. No local
image build is required. The default `main` image tracks development; it is not
a stable-release designation.

## Self-hosted beta configuration

The Compose defaults are intentionally local and use the repository's `data/`
and `library/` directories. To override them, copy `.env.example` to `.env` and
change only the values needed for the host:

| Setting | Default | Purpose |
| --- | --- | --- |
| `FORGE_GAMESHEETS_BIND_ADDRESS` | `127.0.0.1` | Host address that accepts connections |
| `FORGE_GAMESHEETS_PORT` | `8000` | Host port used to open Forge |
| `FORGE_GAMESHEETS_BASE_URL` | unset | Address encoded into FORGE Reprint QR links |
| `FORGE_GAMESHEETS_DATA_PATH` | `./data` | Writable application state |
| `FORGE_GAMESHEETS_LIBRARY_PATH` | `./library` | Source PDF library, mounted read-only |
| `FORGE_GAMESHEETS_IMAGE_TAG` | `main` | Published image channel or fixed release tag |

Published images already include their release, revision, and UTC build date,
visible in Settings and `/health`; users do not need to configure these values.

### Published image deployment

Normal Docker-host installations use the image published from GitHub. Keep
`FORGE_GAMESHEETS_IMAGE_TAG=main` in `.env` for current development builds, or
select a version tag for a fixed release when one is available. Update with:

```sh
docker compose pull
docker compose up -d
```

Do not add host-specific settings to `compose.yml`; keep them in `.env`.

On a Linux Docker host using the default bind mount, prepare the data directory
for Forge's fixed non-root container identity before the first start:

```sh
sudo chown -R 10001:10001 data
```

Do not apply that ownership change to the source PDF library. It only needs to
be readable by the container. Docker Desktop for macOS and Windows normally
handles bind-mount permissions through its file-sharing layer.

For access from another device on a trusted private LAN, set
`FORGE_GAMESHEETS_BIND_ADDRESS=0.0.0.0` in `.env`, then open the configured port
on the Docker host. Authentication is off until local Admin setup: never expose that
port directly to the public Internet or an untrusted network. Remote access
requires an appropriate authenticated proxy, VPN, or network access-control
layer.

After a detached start, allow initialization to finish and verify readiness:

```sh
docker compose ps
curl --retry 10 --retry-all-errors --retry-delay 1 \
  http://127.0.0.1:8000/health
```

## Organizing files

Each first-level directory inside `library/` represents one game. PDFs can be
nested beneath that game directory. The preferred filename is:

```text
<Game Name> - <Document Type> [optional variant].pdf
```

PDFs placed directly in `library/` are ignored because every resource must
belong to a first-level game folder. If you have unidentified or unorganized
documents, place them in a normal staging folder such as `library/Unsorted/`.
Forge displays **Unsorted** like any other game; move the files into their
proper game folders and select **Rescan library** when you are ready. The name
`Unsorted` is a convention, not a reserved folder with special behavior.

Names do not need to be perfect. Unrecognized PDFs remain accessible under
Other, and display metadata can be corrected in the interface without renaming
the source file. Select **Rescan library** after changing library contents.

The preferred artwork method is a square 1024 × 1024 WebP placed at the top of a
game folder using the name `icon.webp` (or `cover.webp`). PNG and JPEG are also
supported. Non-square artwork is center-cropped, and Forge creates an optimized
512 × 512 WebP display cache without changing the library source. Artwork can also be
uploaded through **Edit game entry**. A web upload is normalized into the writable
application-data directory and overrides detected folder artwork; it is not
written back to the read-only library. Include uploaded artwork in application-data
backups. Removing an upload restores any detected folder artwork.

### Game categories and folder hints

Use **Games → Assign game categories** to search/filter games and add, remove,
replace, or clear categories for up to 500 selected games per batch. Every action
shows a confirmation summary before changing data. Admins and Contributors can
use it; Readers cannot edit categories.

Admins can enable **Settings → Library scanning → Import game categories from
folder names** (off by default). A folder such as `Yahtzee (Family) [Dice, Children]`
imports the display title `Yahtzee (Family)` with two categories. Missing categories
are created; parentheses remain title text. This setting affects newly discovered
games only. Existing games require the assignment page's explicit folder-hint
preview and additive application. Rescans preserve manual assignments, and no
folders or source files are renamed. See [category guidance](docs/GAME_CATEGORIES.md).

### Game resource links and BoardGameGeek

Each game entry can store one optional **Official Resource Link** and one
**Alternate Resource Link**, each with its own description. Add or remove them
through **Edit game entry**. Saved links appear as quick-launch actions on the
game page and open in a new tab. Forge accepts complete HTTP or HTTPS addresses
and stores them as application metadata; it does not visit, import, or scan the
destination.

#### BoardGameGeek links without a token

In **Edit game entry**, paste a full BGG game URL containing both its numeric ID
and game-name slug. Forge stores the manual association without fetching or
verifying metadata. Linked games show **View on BGG** and **BGG Files**; unlinked
games show **Search for game at BGG**, using the local display title in a new tab.
Bare IDs and incomplete URLs are not accepted. Local titles and artwork stay
unchanged. See [manual BGG links](docs/BGG_MANUAL_LINKS.md).

You can upload artwork you have permission to use through the existing image
upload. Manual links do not scrape BGG or automatically download images or PDFs.
API enrichment remains a separate, optional feature requiring token configuration.

### Navigation

Desktop navigation groups **Games** (All games, Categories, Assign game categories),
**Quick access** (Pinned, Favorites, Recently used), **Admin** (FORGE Reprints,
Settings, User Accounts), and **Account** (My account and Sign out). **Sheet
Designer** and **History** are separate top-level links. The logo opens Library
home. Mobile Menu shows the same permitted groups with visible links. Admin is
shown only to Admins; Sheet Designer is shown to Admins and Contributors.
Recently used is hidden when its configured limit is zero.

### Sheet Designer

Admins and Contributors can open **Sheet Designer** from the main navigation to
create a new game sheet from scratch. It does not open, alter, or add content to
an existing PDF.
Instead, the editor builds an editable structured FGS document using headers,
score tables, references, checklists, and lined notes. Sections may be reordered,
duplicated, deleted, or paired into two columns. Score rows and checklist items
are editable, and numbered rows such as Round 1 through Round 10 can be generated
in one step. Letter and A4 output are available in portrait or landscape, with a
live single-page preview and overflow warning.

Forge automatically saves each working draft under `data/sheet-designer/`. These
saved drafts are the web Designer's primary working copies and are included when
the Forge `data/` directory is backed up. This is a system-wide shared collection,
similar to the shared PDF library: Admins and Contributors can open, change,
export, duplicate, or delete any saved draft. It is not a private per-user
workspace. Users do not need to export an `.fgs` file after every edit, but
important or difficult-to-recreate sheets should be exported periodically and
before significant shared changes or deletion. **New** creates a separate draft
and **Open** manages saved drafts or imports an FGS file from another location.

**Export PDF** creates the printable result. Designer PDFs are not automatically
added to the indexed library; place an exported PDF in the appropriate game
folder and rescan when it should become a managed resource. **Export .fgs**
downloads the editable source for portable backup, sharing, transfer to another
Forge installation, or use with a compatible future editor. A future published
FGS-library workflow has not yet been defined, so users should not manually move
the Designer's internal working files out of `data/sheet-designer/`.

Designer source uses **FGS**, Forge's portable, JSON-based formal file format for
structured GameSheets. FGS remains independent of the Forge web application so
compatible editors can exchange the same `.fgs` source. See the
[FGS v1 specification](docs/FGS_V1_SPECIFICATION.md), its
[machine-readable JSON Schema](docs/schemas/fgs-v1.schema.json), and the
[Sheet Designer boundary and current limitations](docs/SHEET_DESIGNER_PROTOTYPE.md).

The published image can also run as a Designer-only web application. Set
`FORGE_GAMESHEETS_MODE=designer`; the default and an omitted value remain
`full`, so existing installations are unchanged. Designer mode uses the same
`/data` mount for saved FGS drafts but does not initialize the PDF library,
scanner, main database, accounts, or reprint features. The existing library
mount in `compose.yml` is harmless and ignored in this mode. Designer-only mode
has no account system; retain the default localhost bind unless another trusted
access-control layer protects it.

### Metadata portability

Admins can open **Admin → Metadata portability** to download a temporary ZIP
containing app-managed uploaded game artwork, a complete versioned metadata manifest,
and Windows `.url` and macOS `.webloc` shortcuts. Shortcut names combine the
source game-directory name and recognized link type. Forge streams the ZIP to
the browser and does not retain it.

**Import a Forge metadata export** is the recommended method. It restores URLs,
descriptions, BGG associations, uploaded artwork, and source-directory
relationships. **Scan library shortcut files** is an alternative recovery or
initial URL import that reads recognized shortcuts placed in game folders.
Shortcut scanning discovers URLs but not uploaded artwork or original
descriptions. Both workflows show additions, replacements, unchanged entries,
and skipped entries before confirmation. **Fill empty fields** preserves
existing links and artwork; **Replace recognized fields** overwrites only fields
represented by valid imported records and never clears absent fields.

See [Metadata portability](docs/METADATA_PORTABILITY.md) for the precise export
contents, import policies, folder-based discovery naming, and backup boundary.

### Bulk FORGE Reprint maintenance

Admins can open **Admin → FORGE Reprints** to review current, missing,
stale, and unavailable reprints. Three deliberate operations create only missing
copies, refresh only existing copies, or create/refresh all eligible indexed PDFs.
Forge confirms the number of new and replaced files before starting. Work runs
sequentially as a durable job with progress, safe cancellation after the current
file, interruption recovery, and individual skip/failure details. Source PDFs are
never changed. Every generated copy uses its resource's stable QR address, so
changing access does not require generating another QR code.

Validated generated copies are recorded in SQLite, allowing the maintenance
inventory to use fast database aggregation and a single directory scan instead
of reopening every generated PDF on each visit. The first inventory visit after
this upgrade performs a one-time compatibility pass for existing reprints.

Upgrading from the earlier test-only secure-link design retires `/s/…` QR
addresses. Use **Create or refresh all reprints** once after this upgrade to
replace those experimental copies with the stable `/r/{resource-id}` address.

## Application data and backups

The source PDFs remain in `library/`. The `data/` directory contains the SQLite
database, uploaded artwork, and regenerable caches. Back up both directories:

- `library/` preserves original PDFs and detected artwork.
- `data/` preserves titles, categories, favorites, pins, settings, activity,
  uploaded artwork, Sheet Designer drafts, accounts, sessions, and QR access
  settings. Preserve the hidden `.authentication-required` marker with the rest
  of this directory.

Stop the application before making a simple filesystem copy of `data/`. See
[Backup and recovery](docs/BACKUP_AND_RECOVERY.md) before upgrades or migration.

## Security boundary

FORGE supports optional local Admin, Contributor, and Reader accounts. Existing
installations remain in trusted-operator mode until the operator explicitly
creates the first Admin from a local terminal. An upgrade does not activate
login or change source-library permissions.

### Enable accounts

If Forge will be opened from another device, configure and test its final HTTPS
reverse-proxy address **before** enabling accounts. The deployment guide includes
a tested [Nginx Proxy Manager setup](docs/deployment.md#https-with-nginx-proxy-manager),
including private/self-signed certificates and trusted forwarded headers. Direct
LAN HTTP login is deliberately rejected; localhost HTTP remains supported.

Start the current Forge container, then open a terminal **on its Docker host**.
From the directory containing that installation's `compose.yml`, run:

```sh
docker compose exec app python -m app.accounts create-admin
```

Enter the first Admin username and a new 15–128-character passphrase at the
private prompts. Do not put the passphrase in the command. Successful setup
immediately requires sign-in for the existing library; it does not change PDFs,
categories, or other content. Sign in with that Admin, then open **Admin → User
Accounts** to create Contributor or Reader accounts. QR codes allow direct,
resource-only access by default; an Admin can require sign-in for an individual
resource from its FORGE Reprint page.
There is no default password or web-based initial setup.

Read [Accounts and QR access](docs/ACCOUNTS.md) before activation for HTTPS
requirements, role permissions, recovery, backups, and the effect on previously
printed QR codes. If the container is not running or has a different Compose
service name, follow the deployment-specific instructions instead of changing
the database manually.

For upgrades, `docker compose pull` updates the image only. First update the
repository deployment files and review new `.env.example` options by following
the [existing-installation upgrade procedure](docs/deployment.md#update-an-existing-installation).

The supplied Compose file listens only on localhost. Non-local sign-in requires
HTTPS through a correctly configured proxy. Accounts are not a substitute for
network protection or approval for direct public exposure; do not expose Forge
directly to the Internet.

The library mount is read-only. Forge GameSheets never edits source PDFs.

- **Trusted-operator mode:** until accounts are activated, anyone who can reach
  the application can edit it. Restrict network access before starting.
- **Accounts:** passwords use salted Argon2id hashes, not plaintext. New passwords
  receive offline common-password screening. Sessions expire and account changes
  invalidate affected sessions. These controls do not make public exposure safe.
- **QR access:** every FORGE Reprint uses a stable, resource-only address that is
  public by default. An Admin can require Reader-or-higher sign-in for an
  individual resource, including previously printed QR codes. Downloaded copies
  cannot be recalled.
- **Host and backups:** the database is not encrypted by Forge. Protect data,
  backups, activation markers, and BGG tokens. A container is not a complete
  security boundary; keep the host and images updated.
- **Content:** PDF/image parsing is not malware scanning. Only add trusted files
  you are authorized to use. Browser PDF viewers also need updates. PDF upload
  from the web UI is not implemented; artwork upload is available to editors.
- **Audit visibility:** Admins can review recent account security events
  with actor and target names. This is bounded activity logging, not a complete
  audit trail. General Activity History is retained in SQLite and displayed 50
  events at a time; each library scan creates one aggregate event rather than
  one event per discovered file.

Implementation review and publication safeguards are described separately in
[Development and security](#development-and-security).

## Content rights and responsibility

Forge GameSheets is self-hosted software. It does not provide, sell, upload,
verify the safety or rights of the PDFs placed in an operator's library. The library
operator controls those files and is responsible for ensuring that their
storage, reproduction, use, printing, and distribution are permitted by the
rights holder, applicable license terms, public-domain status, or applicable
law.

The FORGE GAMESHEETS mark on a generated reprint identifies the software used
to prepare that copy. It does not claim authorship or ownership of the source
content and does not imply affiliation with or endorsement by its rights
holders. A FORGE Reprint does not itself grant permission to reproduce or
distribute a source PDF.

QR links point back to the operator's own Forge installation. Depending on its
network configuration, that link may make one resource reachable from other
devices. QR access is public by default. An Admin can require Reader-or-higher
sign-in for an individual resource, and the same printed code responds to the
current setting. This cannot recall downloaded copies. Use the original PDF
when a copy without a FORGE QR link is desired.

## Testing and development

Developers working from local source (including on macOS) build instead of
pulling the published image. The project build command automatically embeds
the checked-out Git revision, a `-dirty` marker when local changes are present,
and the current local build time and time zone:

```sh
./scripts/build
docker compose up -d
```

Build identity overrides for release tooling are `FORGE_GAMESHEETS_VERSION`,
`FORGE_GAMESHEETS_REVISION`, and `FORGE_GAMESHEETS_BUILD_DATE`. They affect image
builds, not the identity of an already-published image.

The build script selects the development image, which includes test tools.
Published images use the smaller runtime stage and do not include those tools.
Run the automated checks in the locally built development container:

```sh
docker compose run --rm app pytest
docker compose run --rm app ruff check .
```

Developer workflow details are in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
Beta testers should follow [docs/BETA_TESTING.md](docs/BETA_TESTING.md).

## Current limitations

- Printing is handled by the browser's PDF viewer; the application cannot
  reliably detect whether a print completed.
- PDF previews show only the first page and may be unavailable for malformed or
  unsupported PDFs.
- Preview and FORGE Reprint processing supports source PDFs up to 250 MB, 500
  pages, and 200 inches in either page dimension. Larger source PDFs remain
  available for original viewing and download but are not processed.
- Game artwork is limited to 25 MB and 40 megapixels before normalization.
  Submissions have a 26 MiB total request limit (including form overhead), a
  30-second receive timeout, and at most four concurrent submissions per process.
- PDF rendering is serialized. Reprints are capped at 250 MiB and previews at
  1 MiB; their combined managed storage budget is 5 GiB. New rendering requires
  free space for the maximum output plus 100 MiB of headroom. Existing copies
  remain usable when those limits prevent new generation.
- FORGE Reprint creates a marked derived copy but does not edit, combine, or
  replace source PDFs.
- Game folders must currently be first-level children of the library root.
- Manual BGG links and external search work without a token. API enrichment is
  experimental and its rollout remains on hold pending approval and token
  distribution guidance. No token is bundled. Configuring one does not verify
  approval or API access; without it, only API controls are unavailable.
- Automatic BGG scan matching and artwork fallback are not yet implemented.
- Structured FGS files, an editor, and a renderer remain future work.
- There is no remote synchronization or cloud backup.
- Production deployment and public network exposure have not been approved.

See the [Phase 1.5 external beta release checklist](docs/PHASE1_5_RELEASE_CHECKLIST.md)
for current prerelease readiness, the
[Phase 1.5 beta release notes](docs/PHASE1_5_BETA_RELEASE_NOTES.md) for the
next prerelease summary, the historical
[Phase 1 release checklist](docs/PHASE1_RELEASE_CHECKLIST.md),
[beta release notes](docs/PHASE1_BETA_RELEASE_NOTES.md) for the timeline-free
Phase 1 summary, and
[browser PDF printing](docs/decisions/001-browser-pdf-printing.md) for the
print-history decision.

## Development and security

FORGE GAMESHEETS is developed with assistance from OpenAI Codex under the
direction of a maintainer with a degree in software development and professional
experience in software testing, test management, and security. Development
includes automated testing and incremental changes, with OWASP ASVS-based
security reviews planned for major releases.
The source is openly available for inspection and contributions.

Before publishing Docker images, [GitHub Actions](.github/workflows/publish-container.yml)
runs automated tests, code-quality checks, and dependency vulnerability audits.
Dependency audit findings block publication. Container scans report High and
Critical findings and block publication for Critical vulnerabilities with an
available fix. The workflow publishes the same image that passed these checks.

These safeguards complement, but do not replace, code review, targeted security
testing, and planned OWASP ASVS-based reviews for major releases. Passing checks
is not a security certification or a guarantee that no vulnerabilities exist.

Documentation checks run with the test suite to catch broken local references,
missing screenshot files, and selected stale feature claims. Major updates also
require a critical-path documentation and screenshot review; automated checks
cannot establish that instructions or screenshots accurately describe every
workflow. See [documentation review](docs/DOCUMENTATION_REVIEW.md).

Operator responsibilities and deployment precautions are described in
[Security boundary](#security-boundary), separate from the development checks above.

Security is a shared responsibility: maintainers work to improve application
safety, while operators manage secure deployment, updates, access, and library
content. Testing and review reduce risk but cannot guarantee security.

## License

Forge GameSheets is available under the [MIT License](LICENSE).
