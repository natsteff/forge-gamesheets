# Local account and QR access review

Date: 2026-09-04. Reviewer: Codex, primary development agent.
Scope: uncommitted opt-in account/role/QR milestone; not a release certification.
Owner review and independent security review remain required before publication.

Follow-up: the owner-authorized [deeper account review](ACCOUNTS_DEEP_SECURITY_REVIEW.md)
records the second AI pass, additional adversarial probes, and outstanding
pre-commit findings. It supersedes the initial validation-only disposition here.

## Implemented boundaries

- Migration 16 adds account, session, throttle, sharing, and security-event tables;
  it does not activate authentication or rewrite existing resource records.
- Local interactive bootstrap and recovery have no public claim endpoint or
  default credentials. A retained activation marker fails closed if account
  state is lost. Restoring an entire old data directory or old application image
  can remove protection; this is an operator-controlled rollback, not a safe
  authentication recovery procedure.
- Routes have explicit permissions and default to Admin when omitted from policy.
  Tests inventory declared routes and exercise denied mutations and sensitive GETs.
- Passwords use Argon2id. Tests cover generic invalid login responses, throttling,
  opaque session digests, expiry, session rotation, account changes, recovery,
  and concurrent attempts to demote the final Admin.
- Existing same-origin mutation controls also protect login, logout, account and
  sharing forms. Non-local HTTP does not present or accept the sign-in form.
- Guest capability requests resolve only their associated resource, check the
  current policy on every endpoint, and cannot browse or generate content.
  Tampering, cross-resource query attempts, revocation, and policy changes are tested.
- Authentication responses are non-cacheable. Shared pages use no-referrer and
  noindex metadata. Application access logging redacts ordinary and encoded share
  paths; proxy logs and downloaded copies are outside this control.

## Verification and remaining review

Final results: 47 focused account/access tests passed; 532 Mac regression tests
passed with the one filesystem-specific test deselected; all 533 tests passed
in the isolated Linux development image. Ruff and `git diff --check` passed.
The Linux run reported two upstream deprecation warnings. The disposable UI
server was stopped after review; no real application container was restarted.

The focused account/access tests and existing regression tests use temporary
databases and synthetic PDFs, not the operator's content. Local Mac testing
excludes the existing case-distinct-directory test on its case-insensitive
filesystem; the complete suite is also run in an isolated Linux container.
Ruff checks cover the full repository. A browser loaded the isolated login
page; a complete interactive/mobile account-management walkthrough remains for
owner review. No production deployment, Docker Test upgrade, live authentication
activation, commit, or publication was performed.

This is a selected-control implementation review, not a complete ASVS assessment.
Before release, perform the planned independent review and an actual configured
HTTPS/proxy walkthrough. General traffic limiting, killable native PDF processing,
MFA/SSO, password-breach screening, comprehensive content auditing, and PDF uploads
remain outside this milestone. Login throttling can temporarily deny legitimate
access and is not a substitute for network controls. QR links have revocation but
no automatic expiry; the owner should evaluate that tradeoff before wider use.

See [account operations](ACCOUNTS.md), [security planning](SECURITY_PLAN.md), and
[the design decision](decisions/004-local-accounts-and-sharing.md).
