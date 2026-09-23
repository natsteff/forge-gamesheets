# Security priorities and future access/upload planning

Security is a primary release requirement. This document includes remaining work
and approved milestones. Local accounts and resource-scoped QR access are now
implemented in the working source; see ACCOUNTS.md and the account review reports.
Future identity providers, MFA, and PDF uploads still require owner approval.
The current supported deployment boundaries remain unchanged: localhost,
trusted LAN, or an appropriately protected proxy/VPN, not direct public access.

## OWASP ASVS assessment and release checkpoints

- [ ] Conduct an initial code and configuration self-assessment against the
  applicable OWASP Application Security Verification Standard requirements.
  Started 2026-09-03: [initial selected-control findings](ASVS_INITIAL_ASSESSMENT.md).
  Full requirement-level coverage and remaining verification are still open.
- Repeat the assessment before every major release, including substantial
  milestone releases during pre-1.0 development. Review changed security
  boundaries when planning authentication, public sharing, or uploads.
- Record the candidate commit, ASVS version, applicable controls, evidence,
  tests, findings, severity, remediation, and remaining gaps. Mark controls
  not tested or not applicable explicitly; do not treat absence of a finding
  as proof of security.
- Cover authorization, file/path safety, input handling, XSS/CSRF, database
  access, PDF/image processing, resource limits, secrets, dependencies,
  container permissions, and deployment configuration.
- Validate findings with reproducible checks and add regression tests for
  fixes. Resolve release-blocking risks before publication and present any
  remaining risks to the owner for an explicit decision.
- At the initial assessment and each major-release checkpoint, use automated
  checks plus a maintainer-led, AI-assisted review. A separate AI pass may be
  requested when useful, but an external professional review is not part of the
  planned release process.
- Describe work publicly as a scoped self-assessment or AI-assisted review,
  not independent certification or proof that all vulnerabilities are absent.

Future release checklists should record the assessment and its remaining limits.

The container publication workflow must run tests, lint, Python and renderer
dependency audits, and a container vulnerability scan before authenticating to
the registry and publishing an image. Known fixed critical vulnerabilities block
publication. High and unfixed critical findings remain visible and require
owner review; a non-blocking scanner result is not automatic acceptance. Record
exceptions explicitly rather than maintaining an unexplained ignore list.

Reference: [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/).

The latest release-focused review is
[the September 11, 2026 security review](RELEASE_SECURITY_REVIEW_2026-09-11.md),
performed against commit `d67cbb2`.

## Secondary review and remaining hardening

The 2026-09-03 owner-authorized secondary AI pass is recorded in
[the review follow-up](SECURITY_REVIEW_FOLLOWUP.md). This is a separate AI review,
not third-party certification.

Dependency policy: every publication must audit resolved Python and locked FGS
Renderer dependencies, then scan the exact runtime image that will be pushed.
Production images exclude
development tools/tests; local builds retain a development target. Do not treat
version ranges as reproducible builds. Before the next major release, review a
lock/update strategy, digest-pinned base images, and immutable Action references
with a deliberate refresh process. Do not freeze old vulnerable dependencies
merely to obtain repeatability.

The FGS PDF CLI uses a supported Node LTS executable copied from the official
multi-platform Node image rather than Debian 13's end-of-life Node 20 package.
The build and publication workflow check the Node 24 major version and minimum
versions that resolve the two reviewed advisories (Node 24.17.0 and Undici
7.29.0), and the workflow records actual Node, Undici, and OpenSSL versions.
Because a copied executable is not recorded as a Debian package, the container
vulnerability scan does not inventory Node: at each release checkpoint, review
newer Node security releases separately. A lower container finding count alone
does not prove the Node runtime is free of vulnerabilities.

The 2026-09-23 local arm64 and amd64 candidate scans reported no critical
findings, no Python high findings after removing build-only pip from the runtime
stage, and 44 high Debian package entries from eight distinct advisories. The
scanner listed no fixed Debian version for those entries. On 2026-09-23 the
owner reviewed the eight underlying advisories and accepted the remaining High
findings for this trusted-network beta release. The affected functions concern
local privileged mount/namespace or ACL operations, systemd-homed, infocmp, and
Perl Archive::Tar; Forge does not invoke those functions in its normal runtime,
which runs without root privileges or Linux capabilities. This is a scoped
release decision, not blanket acceptance for future releases. Refresh the scan
of the exact published image and reassess when Debian packages, the base image,
or Forge's deployment boundary changes.

Remaining decisions/fixes, in priority order:

1. Rendering concurrency and derived-write/storage budgets are implemented and
   published (see deployment guide). Still review isolated,
   killable native-parser execution and a per-client rate policy; serialization
   alone does not stop repeated requests monopolizing the rendering slot.
2. Authenticated BGG redirects are rejected in the published implementation,
   including same-origin redirects. Synthetic transport regression tests verify
   that no redirect destination is contacted and Authorization is not copied.
   BGG rollout remains paused; no token-distribution policy has been approved.
3. Verify an actual protected-proxy deployment when one is used; current tests
   cover trusted versus untrusted forwarded scheme, not a live TLS perimeter.
4. Account operations now record bounded user-attributed events.
   Comprehensive content-change auditing remains future work. Rotating
   access/error logs are operational evidence only; never log tokens or bodies.

## Local login, roles, and QR access — approved implementation

The owner validated the published implementation on the trusted home-hosted
deployment. The permission matrix and migration behavior are in
[Accounts and QR access](ACCOUNTS.md) and [decision 004](decisions/004-local-accounts-and-sharing.md).
Reader, Contributor (previously called Librarian), and Admin are account roles.
QR guest access is a fourth access category, not an account role: it has no
username/password and is limited to one stable resource QR address.

### QR guest requirements

- **Default: allow QR guest access.** In the opt-in authenticated system, a
  resource QR link allows anonymous viewing of its particular
  resource and approved PDF delivery only. It does not grant Reader access to
  the library or permission to edit, upload, or generate/regenerate content.
- **Restrict: require sign-in.** An administrator can restrict an individual
  resource; its QR visitors then require an authenticated Reader, Contributor,
  or Admin. There is no shared "Reader" password.
- Apply the resource's current setting on every QR landing-page and PDF request,
  not just when creating a QR code. Restricting it must also affect previously
  printed codes and direct QR PDF URLs. Previously
  downloaded files cannot be recalled.
- After sign-in, return to the intended resource using a validated local
  destination; do not permit arbitrary redirect URLs.
- The FORGE Reprint page should explain the active access mode and that the
  administrator may change it later. Keep this notice off the printed copy.
- Test both modes, role permissions, direct endpoint access, cross-resource
  attempts, cache behavior, and setting changes on existing links.

Owner validation is complete. Every FORGE Reprint uses a stable numeric
`/r/{resource-id}` address. These addresses are intentionally discoverable rather
than secret bearer credentials: anyone who can reach the installation may try
adjacent IDs and access any resource that remains public. This is an accepted
tradeoff for the trusted home-hosted deployment model, not a design for direct
public-Internet exposure.

- A public QR address exposes only its resource landing page, original PDF, and
  existing generated copy. It does not permit library browsing, history,
  generation, editing, settings, or account access.
- An Admin may require sign-in for an individual resource. The current setting
  is checked on its landing page and both PDF endpoints, including for previously
  printed codes. There is no global QR-access switch.
- The stable address has no secret to rotate or expire. Changing the resource
  policy is the supported way to remove anonymous access; downloaded copies
  cannot be recalled.
- External proxy authentication may still require sign-in before Forge receives
  a request, regardless of the resource setting.
- The FORGE Reprint page explains the current policy. The original PDF remains
  available as the source for printing without a FORGE QR code.
- Tests cover public and restricted access, direct endpoints, cross-resource
  attempts, cache behavior, and changes applied to an existing QR address.

### Bulk reprint maintenance

Bulk FORGE Reprint maintenance is Admin-only and uses the same validated source,
generated-path, rendering-lock, storage-budget, and QR-target services as the
individual workflow. Only one persistent job may be queued or running. Items are
processed sequentially, and cancellation takes effect after the current file so
an atomic output replacement is never interrupted deliberately. Stable QR targets
and current per-resource restrictions are preserved.

Job pages expose resource titles and bounded failure descriptions only to Admins.
They do not store source contents or filesystem paths. Unexpected
errors use a generic message. Database and generated-output backups should be
taken while Forge is stopped so job state and derived files are consistent.

## Possible web uploads and new game entries — review with owner first

Consider a convenient web workflow to add a single PDF to an existing game or
create a new game folder and resource together. Keep direct filesystem loading
as the normal bulk/initial-import option; accepted files remain ordinary files
and SQLite remains an index/state store, not PDF blob storage.

Before approving implementation, review:

- Who may create games or upload, and required authorization/CSRF protections.
- Narrow write permissions or a dedicated intake boundary without casually
  making the entire source-library mount writable or elevating the container.
- Safe game/file names, traversal and symlink defenses, collision handling,
  no silent overwrite, partial-upload cleanup, and failure recovery.
- File type/content validation, size/page/storage/request limits, and isolated,
  bounded PDF processing before automatic indexing or preview generation.
- Clear acceptance/rejection states and automatic discovery of accepted files.

Automatic malware scanning is not currently a requirement. If uploads proceed,
consider a warning asking users to verify files are free of viruses/malware and
an optional link to VirusTotal for manual checking. Explain that submitting a
file to a third-party service can disclose it; do not send files automatically.
User acknowledgement or a clean scan is not a security guarantee and cannot
replace server-side safeguards or establish copyright authorization.

References: [OWASP file upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html),
[VirusTotal sharing model](https://docs.virustotal.com/docs/how-it-works).
