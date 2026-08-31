# Phase 1 beta release checklist

This checklist is the gate for a local Phase 1 beta candidate. It does not
authorize production deployment or public network exposure.

## Scope audit

- [x] Filesystem remains authoritative for PDFs.
- [x] First-level game folders and recursive PDF discovery are implemented.
- [x] Forgiving filename parsing keeps unrecognized resources accessible.
- [x] SQLite stores the index and application state, not PDF contents.
- [x] Games and resources are browsable and searchable.
- [x] PDF view, download, browser printing, and previews are available.
- [x] Manual rescan and incomplete-scan handling are implemented.
- [x] Favorites, pins, Recent, and activity history are implemented.
- [x] Empty, malformed, missing, and unavailable states are represented.
- [x] Responsive and keyboard navigation behavior has automated coverage.
- [x] Category management and persisted application settings are implemented.
- [x] Dynamic generation, QR stamping, accounts, and external enrichment remain
  outside Phase 1.

## Automated verification

- [ ] Build the current image without errors.
- [ ] Run the complete pytest suite.
- [ ] Run Ruff with no findings.
- [ ] Start the Compose service and pass its health check.

Commands:

```sh
docker compose build
docker compose run --rm app pytest
docker compose run --rm app ruff check .
docker compose up
```

Record the tested commit, test count, Docker version, browser, and date in the
release notes before tagging.

## Manual beta-candidate review

- [ ] Start from empty `library/` and `data/` directories.
- [ ] Index a mixed library with clean and imperfect filenames.
- [ ] Search by game and resource title.
- [ ] View, download, preview, and browser-print representative PDFs.
- [ ] Edit metadata and artwork, then restart and rescan.
- [ ] Assign multiple categories and exercise category management.
- [ ] Exercise favorites, ten pins, Recent limits, and History.
- [ ] Verify custom and hidden footer behavior.
- [ ] Remove a test PDF after scanning and verify unavailable behavior.
- [ ] Review desktop, tablet, phone, and keyboard-only navigation.
- [ ] Confirm source PDFs remain byte-for-byte unchanged.

## Documentation and safety

- [x] README describes the implemented Phase 1 behavior.
- [x] Beta testing instructions are present.
- [x] Backup and recovery boundaries are documented.
- [x] Known limitations and browser-print behavior are documented.
- [ ] A stopped-application backup of the test `data/` directory is verified.
- [ ] The planned test-server access boundary is reviewed before deployment.

## Git and public release protection

- [ ] Working tree is clean after the documentation commit.
- [ ] Detailed history is preserved on a clearly named local backup branch.
- [ ] An annotated local backup tag is created.
- [ ] A full Git bundle is written outside the repository.
- [ ] The bundle is verified and can list every reference.
- [ ] A second copy of the bundle exists on separate storage.
- [ ] The consolidated public branch is created separately.
- [ ] Only the consolidated public branch and beta release tag are selected for
  the first push.
- [ ] The owner approves the public summary before repository creation or push.

## Beta blockers

A beta candidate is blocked by any of the following:

- Automated test or lint failure
- Startup or database migration failure
- Source PDF modification
- Arbitrary filesystem access outside configured roots
- Loss of settings or overrides during a normal restart/rescan
- A common browser being unable to view or download PDFs
- No verified backup before Git-history consolidation

Cosmetic issues and explicitly documented Phase 1 limitations should be triaged,
but do not automatically block a small local beta.
