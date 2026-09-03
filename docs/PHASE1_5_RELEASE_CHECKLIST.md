# Phase 1.5 external beta release checklist

This checklist is the release gate for the FORGE Reprint external beta. It does
not authorize direct public-network exposure. Forge GameSheets has no built-in
authentication and remains limited to localhost, a trusted private LAN, or an
appropriately protected proxy or VPN.

Do not move or rewrite the existing `v0.1.0-beta.1` tag. The Phase 1.5 candidate
will receive a new prerelease tag only after every blocking check below passes.

## Candidate record

Record these values before testing:

| Item | Tested value |
| --- | --- |
| Candidate commit |  |
| Proposed version | `v0.2.0-beta.1` |
| Test date |  |
| Tester |  |
| Docker version |  |
| Docker Compose version |  |
| Host operating system |  |
| Desktop browser |  |
| Mobile QR-test device |  |

The candidate commit must match the revision shown in Settings and `/health`.

## 1. Source and backup gate

- [ ] `git status --short --branch` reports a clean working tree.
- [ ] The candidate commit exists on GitHub `main`.
- [ ] The existing Phase 1 detailed-history bundle remains available and
  verified.
- [ ] The current PDF library and application data have stopped-application
  backups on separate storage.
- [ ] The copied `forge-gamesheets.db` and representative library PDFs exist.
- [ ] The backup completed without permission errors or omitted paths.
- [ ] No PDF, database, `.env`, credential, generated output, or private
  screenshot is tracked by Git.

## 2. Automated verification gate

Stop the application before rebuilding:

```sh
docker compose down

./scripts/build

docker compose run --rm app pytest
docker compose run --rm app ruff check .

docker compose up -d

curl --retry 10 \
  --retry-all-errors \
  --retry-delay 1 \
  http://127.0.0.1:8000/health
```

- [ ] Image builds without errors.
- [ ] The complete pytest suite passes.
- [ ] Ruff reports `All checks passed!`.
- [ ] The service becomes healthy.
- [ ] `/health` reports the candidate revision and build date.
- [ ] Settings reports the same build identity.

Record the final test count in the release notes.

### Published-container security gate

- [ ] The GitHub publication workflow completes tests and lint before registry
  login or image publication.
- [ ] The Python dependency audit reports no known vulnerable installed
  dependency; any exceptional finding has an explicit owner-approved treatment.
- [ ] The container scan reports high and critical findings for review.
- [ ] No fixed critical container vulnerability passes the blocking scan.
- [ ] Review high findings and unfixed critical findings rather than treating a
  non-blocking result as evidence that they are harmless.
- [ ] Record the workflow run and scanner results with the release candidate.
- [ ] Complete or refresh the applicable OWASP ASVS assessment and remind the
  owner to arrange an independent review. Do not describe either as
  certification.

## 3. Clean localhost installation

Use a disposable checkout and invented or authorized sample PDFs. Do not reuse
the normal development `data/` directory.

- [ ] Clone the public GitHub repository into a new directory.
- [ ] Confirm the checkout starts at the intended candidate commit.
- [ ] Copy `.env.example` to `.env` without modifying the safe bind address.
- [ ] Create separate empty `library/` and `data/` directories.
- [ ] Build and start Forge using the deployment guide.
- [ ] Confirm the host port listens only on `127.0.0.1`.
- [ ] Confirm the empty-library guidance appears.
- [ ] Add at least two invented or authorized game folders and rescan.
- [ ] Confirm games, PDFs, previews, search, and categories work.
- [ ] Restart Forge and confirm application state persists.
- [ ] Stop Forge and confirm source PDFs are byte-for-byte unchanged.

Remove the disposable checkout only after recording the result and confirming
that it contains no needed test evidence.

## 4. Trusted-LAN installation

Perform this section only on an isolated or trusted private network.

- [ ] Put the bind address, host port, base URL, data path, and library path in
  `.env`; leave `compose.yml` unchanged.
- [ ] Set `FORGE_GAMESHEETS_BIND_ADDRESS=0.0.0.0` intentionally.
- [ ] Set `FORGE_GAMESHEETS_BASE_URL` to an address reachable from the QR-test
  device.
- [ ] Confirm the host firewall exposes only the intended LAN port.
- [ ] Confirm the application is not forwarded directly from the internet.
- [ ] Open Forge from a second LAN device.
- [ ] Generate a FORGE Reprint and scan its QR code from the test device.
- [ ] Confirm the QR opens the intended resource page and never initiates
  printing automatically.
- [ ] Confirm the original and generated downloads both work.

## 5. Representative PDF and print review

Use copies of PDFs and follow the detailed steps in
[the beta testing guide](BETA_TESTING.md).

- [ ] Review Letter and A4 pages.
- [ ] Review portrait and landscape pages.
- [ ] Review a multi-page document.
- [ ] Review a scanned document.
- [ ] Review an unusually narrow document when available.
- [ ] Confirm every footer includes the logo, complete URL, grouped legal
  notice, and unobstructed QR code.
- [ ] Print with **Fit to printable area** and inspect the physical output.
- [ ] Confirm generated output persists across restart.
- [ ] Confirm a source or base-URL change invalidates the stale generated copy.
- [ ] Confirm unsupported input fails without changing the source PDF.

## 6. Upgrade, backup, and recovery walkthrough

Begin from a working older checkout with populated test data.

- [ ] Record the current build identity and verify normal startup.
- [ ] Stop Forge before copying the complete data directory.
- [ ] Preserve any existing `.env` outside the tracked source files.
- [ ] Run `git pull --ff-only origin main` successfully.
- [ ] Rebuild with the new revision and build date.
- [ ] Start Forge and allow database migrations to finish.
- [ ] Confirm Settings, categories, metadata, favorites, pins, history, uploaded
  artwork, and generated-copy state remain available.
- [ ] Rescan and confirm the PDF library remains available.
- [ ] Confirm `compose.yml` has no server-specific local edits.
- [ ] Restore the stopped data backup to a disposable test location and confirm
  that Forge can start from it.

## 7. Documentation and presentation gate

- [ ] README quick start succeeds as written.
- [ ] The detailed deployment guide succeeds on a clean Linux Docker host.
- [ ] Localhost, trusted-LAN, and protected remote-access boundaries are clear.
- [ ] Permissions, NAS mounts, upgrades, backups, and common failures are
  documented.
- [ ] The public screenshot gallery uses only invented data.
- [ ] Screenshots contain no personal paths, hostnames, bookmarks, copyrighted
  PDF content, or private addresses.
- [ ] GitHub displays the dedicated social-preview image correctly.
- [ ] Current limitations and content responsibility are visible.

## 8. External beta package

- [ ] Release notes summarize Phase 1.5 without exposing the private development
  timeline.
- [ ] The testing guide includes FORGE Reprint and build-identification checks.
- [ ] Testers receive the security warning and supported access models.
- [ ] Testers receive an obvious GitHub issue or other approved reporting path.
- [ ] Known limitations distinguish defects from intentionally deferred BGG and
  FGS features.
- [ ] The owner approves the final version, tag, release title, and release
  notes.

## 9. Publication gate

- [ ] Create a fresh annotated prerelease tag at the tested commit.
- [ ] Verify the tag resolves to the candidate commit.
- [ ] Create and verify a Git bundle containing the candidate branch and tag.
- [ ] Copy the bundle to separate storage and verify matching checksums.
- [ ] Push the candidate commit and new tag without moving older tags.
- [ ] Publish the GitHub release as a prerelease.
- [ ] Verify the public repository, README images, release page, installation
  commands, and downloadable source archives.
- [ ] Perform one final fresh clone from GitHub and confirm the expected commit
  and tag.

## Release blockers

Do not publish the prerelease if any of these remain:

- Automated test or lint failure
- Startup, health, or database migration failure
- Source PDF modification
- Unsafe path access or writable source-library mount
- Loss of persistent application state during restart or upgrade
- A broken QR destination or unreadable generated footer
- Direct unauthenticated public-network exposure in the recommended setup
- Missing or unverified data backup
- Private or copyrighted content in the public repository or screenshots
- Installation, backup, or upgrade instructions that fail when followed

Cosmetic issues may be recorded as known limitations when they do not affect
data safety, installation, document access, or the constrained Phase 1.5
workflow.
