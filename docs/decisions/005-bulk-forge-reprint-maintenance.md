# Bulk FORGE Reprint maintenance

Status: owner-approved design baseline; next product milestone.

## Purpose and placement

Add an Admin-only **Settings → Reprint maintenance** utility. It complements
individual resource generation without crowding the main navigation. It is
intended for an initial library load, a generator change, or a public/base-URL
change that requires many stored static FORGE Reprints to be created again.

The source PDFs remain authoritative and read-only. This utility creates or
replaces only derived FORGE Reprint files and their metadata.

## Inventory and operations

Before an operation, show:

- total indexed PDF resources;
- current FORGE Reprints;
- eligible resources without a reprint;
- stale reprints, including generator-version, source, or QR target/base-URL
  changes that the application can identify;
- unavailable or unsupported resources; and
- the estimated scope of the selected operation.

Offer three distinct operations:

1. **Create missing reprints** creates a stored derived copy only where none
   exists and never replaces an existing copy.
2. **Refresh existing reprints** recreates only resources that already have a
   stored derived copy and does not create copies for resources that never had
   one.
3. **Create or refresh all reprints** processes every eligible current PDF,
   creating missing copies and replacing existing ones.

The confirmation page states exact counts where known—for example, 327 total,
241 replaced, and 86 new—and explicitly says original PDFs are untouched. It
also identifies skips such as missing, unsupported, or encrypted input; warns
about estimated time and storage; and explains how active shared QR targets
will be handled. The Admin may cancel before the job starts.

## Durable job behavior

Do not perform a batch in one HTTP request. Reverse proxies and browsers may
time out while rendering continues. Instead:

- confirmation creates a persistent SQLite job and job-item records;
- a background worker processes resources sequentially;
- only one bulk reprint job may be active at a time;
- the progress view reports completed, skipped, failed, and remaining counts;
- closing or reloading the browser does not lose the job or its status;
- cancellation stops safely after the resource currently being processed;
- a container interruption leaves a recognizable interrupted job that an Admin
  can resume or restart deliberately; and
- completion retains a per-resource error report rather than failing the whole
  batch because one PDF could not be processed.

The first implementation may use light browser polling for progress. It does
not require WebSockets.

## Sharing and QR invariants

Bulk regeneration must preserve the access behavior represented by the current
stored reprint:

- an ordinary reprint remains pointed at its ordinary stable resource URL and
  follows the installation's sign-in rules;
- a reprint with an active resource-scoped share retains the active secure
  sharing target;
- a revoked share is never revived; and
- bulk processing must not silently replace a shared QR target with an ordinary
  numeric/sign-in target.

Move QR-target selection out of the individual web route into a reusable service
used by both individual generation and bulk maintenance. This avoids two paths
making different security decisions.

## Processing and storage safeguards

Reuse the existing processing lock and all current validation and resource
limits, including per-file/page/output limits, free-space checks, and the total
derived-storage ceiling. Rendering remains sequential initially. Continue using
atomic output replacement so a failed refresh does not destroy a usable prior
copy.

Eligibility and failures must distinguish at least unavailable source files,
unsupported/encrypted PDFs, validation or rendering errors, storage exhaustion,
and resources changed or removed after the job was planned.

## Expected implementation surface

- a reusable `app/library/reprint_maintenance.py` orchestration/service layer;
- reuse of the renderer and validation in `app/library/reprints.py`;
- SQLite migrations for jobs and job items;
- Admin-authorized maintenance, confirmation, progress, result, cancel, and
  recovery routes;
- a Settings entry plus dedicated server-rendered templates;
- optional lightweight progress polling in the existing JavaScript boundary;
- service, authorization, confirmation, progress, cancellation, interruption,
  sharing-preservation, storage-limit, and failure-isolation tests; and
- README/deployment/backup/beta/security documentation where behavior affects
  operators.

## Validation before release

Exercise all three operations against mixed resources: missing and existing
reprints, ordinary and actively shared QR targets, revoked shares, missing
sources, unsupported PDFs, and injected per-item failures. Specifically verify
regeneration after a generator-version change and after a configured public
base-URL change. Repeat container interruption, cancellation, backup/restore,
and reverse-proxy progress checks before calling the milestone complete.

## Decisions intentionally deferred

The initial version does not require parallel rendering, a general task queue,
scheduled automatic regeneration, or automatic execution during a library
rescan or application upgrade. Those add operational complexity and should be
considered only after real batch sizes and run times justify them.
