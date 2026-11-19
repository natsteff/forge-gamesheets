# First-owner setup: changed-control review

Scope: local first-owner setup implementation on top of deployment checkpoint
`58b65c7`. This is a maintainer-led, AI-assisted review of changed authentication
controls, not independent certification or a complete ASVS release assessment.
Publication still requires the applicable release/security gates.

## Model and boundaries

Fresh full-application data defaults to owner setup before library/QR access.
The deployment setting `FORGE_GAMESHEETS_ACCESS_MODE` explicitly chooses `owner`
or account-free `trusted` access. Trusted mode accepts open editing by anyone who
can reach the service; it never overrides enabled accounts or recovery markers.
Omitted settings preserve existing pre-model open installations; explicit owner
mode requires setup even on those installations. Existing protected
users/roles/sessions remain protected. No default credentials or
console setup token exists. First successful setup claims the installation:
access must be restricted until the operator finishes. This design cannot prove
NAS ownership and deliberately accepts first-visitor claim risk.

Remote browser setup/sign-in requires trusted HTTPS; localhost HTTP remains a
development/tunnel option. Container UID/GID is separate from application users.
Standalone Designer and Studio authentication are outside this change.

## Control evidence

| Control area | Implementation and verification |
| --- | --- |
| Pre-setup authorization | Middleware blocks library, settings, Designer, QR, docs/API routes and writes; only static assets, health and setup remain reachable. Tests inventory normal role routes and exercise fresh-install route denial. |
| Explicit access modes | Fresh/legacy and owner/trusted/omitted combinations tested; invalid modes fail startup; existing accounts and recovery cannot be bypassed by trusted mode. Root Compose retains omitted-setting compatibility; standalone defaults to owner. |
| Transport | HTTPS guard runs before form display or submission; HTTP gets guidance without a password form. Untrusted forwarded-proto headers do not enable setup. |
| CSRF and caching | Existing strict same-origin middleware plus expiring HMAC-signed matching cookie/form token; host-only HttpOnly/SameSite Strict cookie, Secure on HTTPS, 15-minute expiry. Setup/error/redirect responses use no-store. |
| Password processing | Existing bounded username/passphrase validation, common-password screening and Argon2id retained. Confirmation required; form errors do not echo passphrases. Persistent attempt budget precedes password hashing. |
| Single-owner claim | Existing BEGIN IMMEDIATE transaction rechecks account state before creation/activation. HTTP and service concurrency tests allow exactly one owner. Protected setup routes close after activation; forged/stale/replayed submissions cannot replace it. |
| Activation transition | Enabled and setup-required status read in one query/snapshot. A request cannot mix disabled-before with setup-complete-after state to bypass the fresh-install gate. |
| Crash/recovery | Migration 38 persists setup-required state. First-owner installation marker survives interrupted migrations. Marker creation rejects symlinks/nonregular files. Authentication marker remains fail-closed; existing local recover-admin retained. |
| Upgrades | Explicit pre-38 database fixtures preserve existing open workflows. Upgrade and protected-account regression suites retained; no test-only authorization switches added to application code. |
| Security events | Browser setup records the owner-created event and new account identity, not a false local-console actor. No password/session/form token logged. |

Evidence: `tests/test_owner_setup.py`, `tests/test_accounts.py`,
`tests/test_auth_web.py`, migration tests, existing Host/origin/request-limit
suites, full regression/lint, and a disposable real-browser create-owner/sign-in
check. Existing workflow suites explicitly seed pre-38 installation history;
fresh behavior has its own direct application-factory tests.

Owner-setup checkpoint verification: 122 focused authentication/migration tests
passed; its full suite passed 1,110 tests with one skip. Access-mode verification
passed 88 focused tests, with a full suite of 1,134 passed and one skipped.
Ruff and changed-file formatting passed. Container packaging is verified
separately before an image is offered for review. Ruff lint and changed-file formatting
checks passed. Disposable browser setup and sign-in succeeded. Container
packaging verification is a separate local check; no published image or
installed deployment is changed by this source checkpoint.

## Limitations and release follow-up

- Physical Synology HTTPS/proxy and browser activation acceptance remains pending.
  A successful earlier open-mode Synology install does not verify this flow.
- Existing open installations do not become protected automatically.
- A stopped, complete application-data backup is required before upgrading;
  reverting an image alone after migration 38 is unsafe. Restore its matching
  pre-upgrade data/configuration and retained image to roll back.
- Full ASVS requirement coverage, independent review and internet-exposure
  hardening are not claimed. Keep the supported trusted/private/protected-proxy
  deployment boundary.
- Synology guidance now includes the owner-reported installation adjustments,
  optional `.env`/direct YAML, and BGG configuration; other NAS/GUI combinations
  and protected Synology owner setup still require installation acceptance.

References: [OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## Moving-beta merge checkpoint — 2026-11-19

The owner reported a successful fresh installation of the test branch and
explicitly authorized merging and publishing after the remaining scan findings
were disclosed. This is approval to proceed with this moving-beta update, not
blanket acceptance of future findings or a completed wider-release assessment.
No existing installation is automatically upgraded by this publication.

The previous candidate `13adf0d` (workflow `44432107468`) reported zero Critical
and 47 High package entries per architecture, spanning 11 OS advisories, with
no fixed package versions listed. Previous acceptance covering eight advisories
is not represented as acceptance of all eleven. The new publication must scan
both architectures again; any changed findings remain subject to review.
The SQLite advisories concern FTS/session changesets; no use of those APIs was
found in application code. This is not proof of non-exploitability. Container
hardening and the private-network boundary do not eliminate dependency risk.
Physical production migration, metadata import acceptance, and full ASVS
wider-release review remain outstanding. Preserve the previous image plus a
matching stopped-data backup before upgrading an existing installation.
