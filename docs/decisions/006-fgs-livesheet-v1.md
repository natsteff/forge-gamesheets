# 006 — FGS LiveSheet v1 uses temporary permission-scoped sessions

## Status

Accepted for incremental implementation. The persistence and authorization
foundation plus Designer row recognition and reusable readiness configuration
are implemented; public launch, invitation, live-update, and end-game interfaces
remain subsequent milestones.

## Purpose

FGS LiveSheet turns a reusable GameSheet into a temporary, browser-driven score
sheet for a game in progress. It does not replace the printable GameSheet or
store runtime scores in its FGS source.

Keep three concepts separate:

1. A **GameSheet** is the reusable FGS document.
2. **LiveSheet-ready configuration** describes reusable interactive behavior.
3. A **LiveSheet session** contains temporary player names, permissions, scores,
   checklist state, and game notes for one game in progress.

Making a GameSheet LiveSheet-ready is non-destructive. Starting a game takes an
immutable, validated FGS snapshot so later Designer edits cannot rearrange an
active session. Frequently used LiveSheet-ready documents may be listed by
recent launch time later without retaining earlier participants or results.

## Launch modes and permissions

The host selects a mode before sharing an invitation.

### Single scorer

- The host edits every player name and score.
- The host edits milestones, checklists, and game notes.
- Everyone joining through the invitation receives a live read-only view.

### Individual scoring

- The host claims one player position and can edit only that position's name
  and score column.
- Every other participant claims an available position and can edit only that
  position's name and score column.
- Everyone sees the complete sheet.
- Only the host edits milestones, checklists, and game notes, controls joining,
  releases positions, or ends the session.
- Host status never permits editing another player's name or scores.

The shared invitation allows read access and, in individual mode, claiming an
available position. It never contains a claimed player's private editing token.
Player selection alone is not authorization.

## Invitations

The host interface will present the same invitation as both a QR code and a
copyable URL. A native browser share action may also be offered. This supports
text messages, accessibility, and testing without a QR scan.

Host, invitation, and claimed-player credentials are cryptographically random
bearer secrets. Store only their hashes. Never include scores or player names in
an invitation URL, and prevent application logs from retaining these secrets.
Locking or regenerating an invitation stops new claims without automatically
disconnecting already claimed players.

## LiveSheet v1 score calculations

Score rows named exactly `Total` or `Grand Total`, ignoring capitalization and
extra surrounding whitespace, are calculated rows. The UI must visibly
distinguish them and must not allow score entry in their cells.

- `Total` adds ordinary numeric rows since the previous `Total`.
- `Grand Total` adds every preceding `Total`; when none exists, it adds the
  ordinary rows preceding it.
- Other calculated rows never count as ordinary score input.
- Blank cells count as zero while remaining visually blank.
- Negative integers represent penalties. LiveSheet v1 uses integer addition
  and provides no executable or arbitrary formulas.

The Designer's separate **Include a summary row** checkbox will be retired when
the LiveSheet row editor is implemented. A visible `Total` row becomes the one
consistent way to request a calculated total. New tables may include one by
default, and deleting it produces a table without a total.

Complex repeated scoring columns such as `×1`, `×2`, and `×3` within one player
are a separate future capability. Do not confuse those with player ownership.

## Temporary state and lifetime

Active sessions use dedicated SQLite tables rather than memory or the shared FGS
draft directory. This lets an in-progress game survive an ordinary container
restart without turning it into a permanent library record.

LiveSheet v1 is initially a full-application capability because its public
invitations depend on the configured base URL and its host launch depends on
Forge's Contributor/Admin access control. Enabling it in Designer-only mode is
deferred until that mode has an intentional host-authentication and network
exposure design; do not silently expose host controls from its unauthenticated
standalone surface.

- Inactivity expiration: 12 hours.
- Absolute lifetime: 24 hours from launch.
- The host may end a game earlier.
- Ending or expiration deletes the FGS snapshot, player names, score values,
  notes, checklist state, and all bearer-token hashes.
- A data-free tombstone may retain only the random session ID and end time for
  24 hours so old links can say the session ended instead of appearing broken.
- Cleanup runs at application startup and periodically once routes are exposed.

Deletion is an application-lifecycle guarantee, not forensic erasure. A backup
taken during an active game may contain that session until the operator's backup
retention expires. Documentation must state this before the feature is exposed.

Before ending, the host will be offered explicit print or download actions.
LiveSheet v1 does not automatically retain completed-game history. Saving named
results, winners, or reusable completed sessions is intentionally deferred.

## Update transport

The initial browser implementation should favor simple bounded polling or
Server-Sent Events. WebSockets and offline synchronization are deferred until
real multiplayer behavior demonstrates that their additional reverse-proxy,
reconnection, and conflict complexity is justified. The server remains the
authority for permissions, values, totals, and revision ordering.

## Implementation sequence

1. Durable temporary-session schema, immutable snapshots, token hashing,
   permission enforcement, calculations, expiration, and deletion.
2. Designer row semantics and LiveSheet-ready configuration.
3. Authenticated host launch/setup interface.
4. QR and copyable invitation, read-only viewer, and player-position claiming.
5. Live score, milestone, and note interface with synchronized updates.
6. End-game review, explicit print/download, deletion, and operational cleanup.

Each milestone requires narrow authorization, validation, expiry, concurrency,
and failure tests before the next public capability is exposed.
