# 003 — BoardGameGeek is an optional enrichment service

## Status

Accepted for the Phase 2 roadmap. Before implementation, verify current API,
authorization, rate-limit, and URL behavior against official BoardGameGeek
documentation and propose the affected code and migration.

## Decision

BoardGameGeek (BGG) is Forge GameSheets' primary external source for game
identification, reference metadata, representative artwork, and navigation to
game-specific community Files.

A local Forge game remains the primary object. Its library content remains
filesystem-authoritative. BGG enrichment must not become a requirement for
normal library discovery or use.

Use the official BoardGameGeek XML API2 where possible. Do not build an HTML
scraper or depend on undocumented/private APIs unless a future decision
explicitly approves it.

## Service boundary

BGG behavior must live behind a distinct service/module rather than being
scattered through the scanner, persistence, image, and UI layers. Its boundary
should provide capabilities equivalent to:

```text
search_game(name)
get_game(bgg_id)
get_image(bgg_id)
game_url(bgg_id)
files_url(bgg_id)
```

Exact names should follow the codebase architecture. The boundary owns HTTP
requests, XML parsing, timeouts, response validation, URL construction,
authorization/configuration, caching policy, and external failure translation.

No credentials or personal secrets may be embedded in source code. Required
configuration belongs in the established environment/configuration system and
must be documented for deployments.

## Matching during library discovery

For entries where BGG lookup is enabled, Forge should:

1. Discover the local entry through the existing filesystem scan.
2. Normalize its detected name for BGG search without changing the local name.
3. Search XML API2.
4. evaluate candidates using an explicit, tested confidence policy;
5. link only a sufficiently confident result automatically;
6. preserve ambiguous or weak results for manual resolution;
7. persist the selected BGG ID and relationship state;
8. retain manual matches on later scans until the user changes them.

The model must cleanly represent behavior equivalent to:

- matched;
- unmatched;
- ambiguous/requires review;
- manually matched.

Exact database fields and enums will be proposed after the existing schema and
repository layer are reviewed. Forge must never silently choose a materially
uncertain match.

An unsuccessful lookup never blocks import. If BGG is unavailable, rate
limited, rejects authorization, returns malformed data, or has no useful match,
the local scan continues and the entry remains usable. The UI should explain
the enrichment state and permit a later retry.

## Lookup applicability

BGG lookup is enabled by default for ordinary library entries. Users must be
able to disable it for an entry where BGG does not apply, retry it, manually
select a match, change an incorrect match, or unlink it.

Use a concept such as `bgg_lookup_enabled`, not `is_board_game`: a tabletop RPG
may have a useful BGG record while a homemade board game may not.

Preserve a future configuration model in which a scan path supplies the default
BGG behavior and an individual entry can override that default. Path-level
configuration is not required in the initial implementation.

## Persistent data and caching

The important persistent external identifier is `bgg_id`. Cache only metadata
that improves normal use, matching, or failure tolerance, such as:

- BGG game name;
- image and thumbnail references;
- match status and confidence;
- whether lookup is enabled;
- last refresh or lookup timestamp;
- image provenance where useful.

Publication year may help distinguish search results without needing permanent
storage unless implementation demonstrates a practical reason.

Derive BGG URLs from the stored ID instead of redundantly persisting them.
After a match is established, scans should not repeatedly search BGG unless the
user requests refresh, removes the association, materially relevant source data
changes, or another documented invalidation rule applies.

Do not duplicate the BGG database. Previously enriched games remain displayable
and usable while BGG is offline.

## Artwork behavior

Local artwork has priority:

- If local artwork exists, keep it and still perform/store BGG matching.
- Do not automatically replace local artwork with a BGG image.
- Make the associated BGG image available as an explicit replacement action.
- If local artwork is absent and the match is reliable, Forge may use the BGG
  image as initial fallback artwork.
- Preserve image provenance if the artwork model tracks it.

A valid stored BGG ID should be sufficient for a later **Use BGG Image** or
**Replace with BGG Image** action; do not require a redundant search.

## User-facing actions

For a linked entry, provide actions equivalent to:

- Open on BoardGameGeek;
- Open BGG Files;
- Use or replace with BGG image;
- Change BGG match;
- Unlink BGG match.

For an unlinked entry, provide **Find on BGG**. Search results must show enough
information to distinguish similarly named games; publication year is useful
for this purpose.

Game and Files URLs should be derived from the BGG ID, but their current routing
must be verified before hard-coding them.

## Relationship to FGS and community sharing

The BGG ID is an optional common external identifier that may connect a local
game, local resources, future FGS files, rendered GameSheets, and BGG pages.
Neither a Forge game nor an FGS file requires a BGG association.

Forge will not become a public content host. A future workflow may help users
navigate to BGG Files and independently share both rendered GameSheets and
editable `.fgs` sources. Investigate `forgegamesheets` as the canonical naming
or tagging convention and `fgs` only as secondary shorthand.

If BGG lacks an official Files discovery API, external navigation is sufficient.
Do not scrape the Files pages. Do not automate file uploads unless BGG exposes
an approved API and the feature receives a later explicit decision.

## Implementation sequence

Before broad code changes:

1. Review the current game/database model and migration system.
2. Review scanning and reconciliation behavior.
3. Review local/uploaded artwork detection and storage.
4. Review configuration and deployment conventions.
5. Review test fixtures and external-service mocking patterns.
6. Propose the service interface, schema migration, matching policy, cache
   invalidation, failure states, and affected files.

Then implement in focused increments:

1. BGG configuration and isolated XML API2 client with mocked tests.
2. Persistent association, match state, and cache metadata migration.
3. Resilient matching/enrichment coordination that cannot fail local scans.
4. Manual resolution and retry workflow.
5. Game and Files navigation.
6. Artwork fallback and explicit replacement.
7. Deployment, configuration, privacy, and failure documentation.

The implementation must remain small enough to test at each boundary and must
not pull the FGS schema, editor, renderer, community repository, or automated
BGG upload into Phase 2.
