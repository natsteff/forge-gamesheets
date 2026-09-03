# Security review follow-up — 2026-09-03

Baseline: `d570692`, plus the pending publication-gate changes. The owner
authorized a separate read-only secondary AI review. The primary agent validated
findings against source and isolated tests. No live library, real credentials,
Docker Test, or destructive load tests were used. This is selected-control
review, not complete ASVS verification or certification.

## Findings and treatment in this working change set

- **Medium: unbounded multipart reception.** The artwork limit applied only
  after form parsing. Added pre-parsing 26 MiB request admission, actual streamed
  byte counting, bounded scratch storage, 30-second receive timeout, and four
  concurrent mutation admissions per process. Host/origin rejection precedes
  body reception. Tests cover declared, undeclared/chunked, misleading and
  malformed lengths, replay, disconnects, and admission overload.
- **Medium: repeated expensive processing/storage consumption.** Confirmed;
  partially addressed in the subsequent working change set. Preview/reprint
  rendering is serialized with thread and shared-data worker locks. Bounded
  output writers enforce per-file caps; preflight and pre-publication checks
  enforce free-space headroom and a combined derived-storage budget. Regression
  tests cover actual codec overflow, low space, cache budget, worker contention,
  partial-write cleanup, old-copy preservation, and visible failed regeneration.
  A killable native-parser timeout, per-client rate policy, and host filesystem
  quotas remain open; application checks cannot reserve space against unrelated
  host writers.
- **Medium, latent: BGG token forwarding on redirect.** Confirmed that the
  current urllib redirect implementation copies Authorization to redirected
  requests. Addressed in the subsequent pending client change: a dedicated
  opener rejects redirects, including same-origin targets, and Authorization
  uses a non-forwarded request header as defense in depth. Redirect response
  handles are closed and errors expose neither tokens nor redirect targets.
  Tests exercise the real opener/redirect machinery with a mocked transport,
  synthetic tokens, and 301/302/303/307/308 responses. No actual credential or
  BGG network request was used. BGG activation and rollout remain paused.
- **Defense in depth: development tools in runtime.** Split runtime and local
  development stages. Published images select runtime; the existing Mac build
  script selects development so container test commands remain available.
- **Proxy trust.** Added an explicit conservative Compose setting and tests
  showing that only a configured proxy peer can supply the external scheme.
  Real proxy/TLS perimeter validation remains an operator-specific check.
- **Dependencies/logs.** Publication gates are pending in the same worktree.
  Resolved version locking and immutable build inputs remain planned. Docker
  log rotation is configured; operational logs are not a security audit trail.

The secondary agent also reviewed the new request middleware and caught a
disconnect-propagation defect; it was fixed with a regression test before handoff.

## Future access boundary

Numeric `/r/{id}` URLs are navigation in today's trusted-network/no-login model.
They must not become anonymous authorization after login is introduced. The
existing plan requires random, revocable, resource-scoped sharing capabilities
and authorization on every destination before that feature proceeds.

## Assurance limits

Subsequent rendering/storage change verification: 29 focused tests passed;
the host suite passed 458 tests with the same case-sensitive-filesystem test
excluded, and lint/diff checks passed. These tests use small synthetic PDFs and
simulated storage failures rather than filling a real disk. The new code has
not been committed, pushed, or deployed to Docker Test.

Verification for this working change set: 446 tests passed in an isolated Linux
container using the already-installed development dependencies and current
source mounted read-only, with no network or real library mounts. Host checks
passed 445 tests with the known case-sensitive-filesystem test excluded; lint,
Compose configuration validation, and diff whitespace checks passed. Docker Hub
timed out resolving the Dockerfile frontend, so fresh runtime/development image
builds and runtime contents inspection remain unverified. Publication scans have
not run on GitHub because these changes have not been committed or pushed.

XSS escaping/CSP, Host validation, origin checks, path/symlink defenses, and
token representation redaction were positively reviewed. These observations
do not establish absence of other vulnerabilities. Remaining findings stay
visible in [the security plan](SECURITY_PLAN.md); the owner should arrange a
human review for stronger assurance before broader exposure.
