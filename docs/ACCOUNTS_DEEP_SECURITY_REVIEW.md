# Account and QR security review — pre-commit

Date: 2026-09-04. Baseline: `2d610a98ae82d61145b0950e0719c9f8d49bc14b`
plus the uncommitted local-account/QR implementation and documentation.
Reviewers: primary Codex agent and a separately tasked Codex security reviewer.
This is an independent second AI pass, not an external human audit, complete
ASVS verification, or certification. No application fixes were made in this review.

## Decision

No direct login bypass, Reader-to-Admin escalation, or QR-to-library access
bypass was found in the inspected code and synthetic tests. That does not
establish their absence. **Hold the account-feature commit for the targeted
fixes below and an explicit password-policy decision.** The publication gate
does not check these application-specific behaviors.

## Findings

### AR-1 — Anonymous attempts can block an authenticated Admin's confirmations

Priority: fix before commit. Severity: moderate availability impact, dependent
on an untrusted client being able to reach the login endpoint. Not an account
takeover or disclosure.

`app/accounts.py:178–206, 209–213, 300–301` uses the same username, client, and
global throttle for public login and signed-in password confirmation. Successful
checks also consume the budget. A successful Admin login followed by nine
unauthenticated wrong-password submissions for that username exhausts its ten
checks. The still-signed-in Admin can view account settings, but a correct
password confirmation for QR policy changes is rejected with “Too many attempts.”
This also obstructs account/password/sharing controls until the window expires.
Ten failed attempts can similarly block a fresh login without needing a password.
The global budget can affect all accounts when attempts originate from enough
client addresses; a shared proxy/NAT address can reduce the effective limit further.

Reproduction: use a temporary installation and Admin, sign in, submit nine
`POST /login` requests with the same username, a wrong password, and no session
cookie, then submit `/settings/qr-access` with the original authenticated cookie
and correct current password. The final request returns HTTP 400 and the throttle
message; normal signed-in settings viewing still succeeds.

Recommendation: separate public-login and authenticated-confirmation budgets,
retain bounded password work and anti-brute-force controls, and explicitly design
targeted/global lockout behavior. Do not simply remove throttling. Add regression
tests showing anonymous failures cannot exhaust an existing session's security
controls, and verify legitimate and abusive behavior across users/client addresses.

### AR-2 — Alternate-encoded login return URLs evade share-token log redaction

Priority: fix before commit. Severity: low, secret-handling defect.

`app/access.py:185–193` redacts literal `/s/` and fully encoded `%2fs%2f`, but
misses a valid query such as `/login?next=%2F%73%2F<TOKEN>` or mixed `/s%2F`.
The application decodes the value to `/s/<TOKEN>` and accepts it as a local
return destination. Uvicorn retains the raw query string in its access-log path,
so the current filter leaves the capability token in the log.

Both reviewers reproduced this using Uvicorn's actual
`get_path_with_query_string` helper and the configured logging filter; the primary
review also verified the login endpoint accepts that encoded destination.
Ordinary percent-encoded path segments alone are **not** a reproduced leak:
Uvicorn quotes the decoded path, which the existing filter catches.

This finding does not discover or mint a token. A token-bearing alternate URL
must already be supplied, and a reader of the resulting log could then obtain it.
Recommendation: omit sensitive login query values or redact them after canonical
parsing; verify normal, mixed, nested, and invalid encodings with real log formatting.
Continue protecting proxy logs separately; application filtering cannot govern them.

### AR-3 — Common-password screening is absent

Status: explicit policy gap; decide before commit, not a demonstrated bypass.

`app/accounts.py:86–89` accepts any 15–128-character value. A synthetic
`passwordpassword` value was accepted and verified. Length and Argon2id hashing
are useful but do not establish resistance to guessable passwords. The selected
ASVS password review identifies common-password screening as missing; broader
breached-password screening was already deferred in the implementation notes.

Recommendation: add an offline common-password blocklist across bootstrap,
recovery, account creation, and password changes, or record an explicit scoped
beta exception with the owner. Do not send users' passwords to a third party.
MFA remains a separate approved-scope decision, not an implied requirement to
implement it during these fixes.

## Evidence and coverage

- Existing repository suite: **533 passed**, one case-distinct-directory test
  deselected on the Mac's case-insensitive filesystem. Ruff passed. The run had
  upstream deprecation warnings and a denied pytest-cache write warning; the
  extra probes ran with caching disabled. Linux was not rerun for this read-only
  review; prior implementation evidence remains in the earlier review document.
- Primary additional probes: **26 passed**, covering protected GET routes for
  anonymous/Reader/Contributor clients, path aliases and traversal attempts,
  alternate methods, restricted QR Range/conditional requests, indexed symlinks,
  cross-origin/invalid-host account mutations, raw forwarded-header spoofing,
  plus reproductions of AR-1, AR-2, and AR-3. “Passed” includes assertions that
  reproduce the current weaknesses; it does not mean those weaknesses are fixed.
- Second reviewer: existing account/auth HTTP suite **47 passed**; separate
  synthetic probes verified stale privileged-cookie rejection after demotion,
  disabled Reader-cookie rejection, recovery invalidation of cookies and old
  passwords, exactly-one concurrent first-Admin creation, and rejection of an
  old-password login racing recovery after password verification.
- Tests used temporary directories, invented credentials, and synthetic PDFs.
  No live server, real library, existing account database, Docker Test deployment,
  GitHub publication, or external BGG service was tested or changed.
- Local reproduction artifacts: `/tmp/test_forge_deep_accounts.py` and
  `/tmp/forge-independent-account-review.py`. These are temporary review probes,
  not committed regression tests. Convert relevant probes into regression tests
  alongside the approved fixes.

## Selected ASVS 5.0.0 mapping

This is a selected-control review, not a claim of complete chapter/level coverage.

| Controls | Scoped result |
| --- | --- |
| 6.1.1, 6.3.1 | Throttle documented/implemented; malicious lockout concern AR-1 remains |
| 6.2.1–6.2.3, 6.2.5–6.2.10 | Source/tests support length, password change and confirmation, character support, masking/password-manager attributes, exact verification and no forced periodic rotation; no full browser/password-manager matrix |
| 6.2.4, 6.2.12 | Common/breached-password screening missing; AR-3 |
| 7.2.1–7.2.4, 7.3.1–7.3.2 | Server-side random session validation, rotation, idle and absolute expiration covered by source and tests |
| 7.4.1–7.4.3, 7.5.1 | Logout/account changes/recovery invalidate sessions; sensitive account operations require confirmation in reviewed flows |
| 8.1.1, 8.2.1–8.2.3, 8.3.1 | Shared-library permission matrix documented; server-side route/service checks and resource-scoped guest probes found no bypass |

References: [ASVS 5.0.0 authentication](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md),
[session management](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md),
[authorization](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x17-V8-Authorization.md).

## Residual boundaries and next checkpoint

Actual HTTPS termination, trusted-proxy configuration, browser/mobile interaction,
and external perimeter behavior still require deployment-specific verification.
Raw spoofed forwarding headers were rejected in the isolated app tests; this
does not prove a real proxy is configured correctly. Shared URLs have no automatic
expiry and expose the current source resource, not a frozen snapshot. Revocation
cannot recall downloads or cancel a response already admitted. Full content
auditing, per-client general traffic limits, native-parser process isolation,
session-list UI, MFA/SSO, and PDF uploads remain outside this review's fixes.

After approved remediation, rerun the adversarial probes and full suite, update
this disposition, and obtain owner approval before committing. For stronger
assurance before wider/untrusted exposure, arrange a human security review;
the separate AI pass is not a substitute for independent professional assurance.
# Follow-up fixes (2026-09-04)

AR-1: Password confirmations now use a separate authenticated-account budget;
anonymous login attempts cannot consume it. Public login denial-of-service limits
remain a deployment consideration. Confirmations allow 10 attempts per 15 minutes,
including successful confirmations, to bound password verification work.

AR-2: Application access logging now omits all query strings, covering mixed and
nested encodings of QR redirect targets, while retaining shared-path redaction.
Reverse-proxy logging remains the operator's responsibility.

AR-3: New passwords are checked offline against the vendored Django 5.2.6 common
password list (with license/provenance), repeated common words, and repeated single
characters. Existing passwords are not rejected at login. This is limited common
password screening, not a complete compromised-password corpus or certification.

Regression coverage includes throttle isolation and enforcement, encoded redirect
redaction, common-password rejection, and legacy-password compatibility.

Verification: 55 focused account/web tests passed; full Mac run 541 passed with
the existing case-sensitive-filesystem test deselected. Ruff and diff whitespace
checks passed. The vendored 19,640-entry list matches the downloaded source hash.
