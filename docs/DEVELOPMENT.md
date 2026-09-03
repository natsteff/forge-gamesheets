# Local development

Forge GameSheets uses Docker Compose as the supported development workflow.
Python 3.13 and all development dependencies are installed inside the image, so
a separate host Python environment is optional.

## Start the application

```sh
docker compose up --build
```

Open <http://localhost:8000>. Stop the attached service with `Ctrl+C`.

The Compose service mounts:

- `./library` at `/library` as read-only source content
- `./data` at `/data` as writable application state

Both directories must exist. Their contents are ignored by Git.

## Run checks

Stop the attached application first, then run:

```sh
./scripts/build
docker compose run --rm app pytest
docker compose run --rm app ruff check .
```

Run focused tests while developing when useful, but run the full suite and lint
checks before each completed milestone.

## Database migrations

SQLite migrations run automatically during application startup. Never edit an
already committed migration. Add the next numbered migration and cover both a
new database and the upgrade behavior with tests.

Back up `data/` before testing an upgrade against important local state. Source
PDFs are not stored in SQLite.

## Repository rules

- Keep `main` runnable and changes focused.
- Use `compose.yml`; do not add alternate Compose filenames.
- Preserve the filesystem as the source of truth for PDF content.
- Do not commit real PDFs, databases, secrets, caches, or generated output.
- Treat stored paths, filenames, form values, and uploads as untrusted input.
- Do not begin production deployment as part of local development.

Use short imperative commit subjects, such as:

```text
Add library category management
Document Phase 1 beta workflow
Handle unavailable PDF previews
```

## Release preparation

Follow [PHASE1_RELEASE_CHECKLIST.md](PHASE1_RELEASE_CHECKLIST.md). Public-history
consolidation, GitHub publication, and beta tagging happen only after the local
history has been backed up and verified separately.
