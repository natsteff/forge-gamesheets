# Documentation release checks

Documentation is part of the release, not a follow-up task. Run the automated
documentation tests on every change through the normal pytest publication gate.
They check local Markdown/image references and selected obsolete capability claims.
They do not validate external services, screenshot appearance, or every statement.

For every major update (including significant beta milestones), review:

- README feature list, navigation labels, screenshots, limitations, and setup.
- Fresh image pull/start, first library scan, optional folder hints, and rescan.
- Bulk categories: permissions, filters, confirmation/cancel, and source preservation.
- Account bootstrap on an existing installation, role restrictions, recovery,
  session invalidation, and QR guest allow/restrict/revoke behavior.
- Manual BGG URL validation, correct Game/Files links, and no-token operation.
- Reprint generation/download/regeneration and source-file preservation.
- Deployment HTTPS/proxy boundaries, data permissions, backup/restore, and build identity.
- Screenshots at desktop and mobile sizes using invented content only. Never
  capture real accounts, library PDFs, credentials, or live guest-share tokens.
- Consistency among README, deployment/accounts/category/BGG guides, current
  release notes, and the project plan. Historical release documents should be
  explicitly identified as historical instead of silently rewritten as current.

Record the candidate revision, tests run, screenshots refreshed, manual paths
checked, known gaps, and owner approval in release evidence. Remind the owner to
perform the independent/ASVS-focused review before major release approval.
No green automated check replaces that review. Do not publish while documentation
describes unverified critical-path behavior as confirmed.
