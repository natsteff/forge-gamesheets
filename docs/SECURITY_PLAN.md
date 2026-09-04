# Security priorities and future access/upload planning

Security is a primary release requirement. This document includes remaining work
and approved milestones. Local accounts and resource-scoped QR sharing are now
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
- At the initial assessment and each major-release checkpoint, explicitly
  remind the owner to arrange an independent review. Offer a secondary AI
  reviewer for a separate pass, with findings independently verified, and
  discuss a human security review for stronger assurance before wider exposure.
  Do not silently launch a second reviewer or commission external work.
- Describe work publicly as a scoped self-assessment or AI-assisted review,
  not independent certification or proof that all vulnerabilities are absent.

The reminder is tied to release work, not a scheduled notification. Future
release checklists should include both the assessment and owner reminder.

The container publication workflow must run tests, lint, a Python dependency
audit, and a container vulnerability scan before authenticating to the registry
and publishing an image. Known fixed critical container vulnerabilities block
publication. High and unfixed critical findings remain visible and require
owner review; a non-blocking scanner result is not automatic acceptance. Record
exceptions explicitly rather than maintaining an unexplained ignore list.

Reference: [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/).

## Secondary review and remaining hardening

The 2026-09-03 owner-authorized secondary AI pass is recorded in
[the review follow-up](SECURITY_REVIEW_FOLLOWUP.md). This is a separate AI review,
not third-party certification or a substitute for a human review.

Dependency policy: every publication must audit resolved Python dependencies and
scan the exact runtime image that will be pushed. Production images exclude
development tools/tests; local builds retain a development target. Do not treat
version ranges as reproducible builds. Before the next major release, review a
lock/update strategy, digest-pinned base images, and immutable Action references
with a deliberate refresh process. Do not freeze old vulnerable dependencies
merely to obtain repeatability.

Remaining decisions/fixes, in priority order:

1. Rendering concurrency and derived-write/storage budgets are now implemented
   in the pending change set (see deployment guide). Still review isolated,
   killable native-parser execution and a per-client rate policy; serialization
   alone does not stop repeated requests monopolizing the rendering slot.
2. Authenticated BGG redirects are now rejected in the pending change set,
   including same-origin redirects. Synthetic transport regression tests verify
   that no redirect destination is contacted and Authorization is not copied.
   BGG rollout remains paused; no token-distribution policy has been approved.
3. Verify an actual protected-proxy deployment when one is used; current tests
   cover trusted versus untrusted forwarded scheme, not a live TLS perimeter.
4. Account and sharing operations now record bounded user-attributed events.
   Comprehensive content-change auditing remains future work. Rotating
   access/error logs are operational evidence only; never log tokens or bodies.

## Local login, roles, and QR sharing — approved implementation

The owner approved local implementation and testing, not live activation or
publication. The implemented permission matrix and migration behavior are in
[Accounts and QR sharing](ACCOUNTS.md) and [decision 004](decisions/004-local-accounts-and-sharing.md).
Reader, Contributor (previously called Librarian), and Admin are account roles.
QR guest access is a fourth
access category, not an account role: it has no username/password and is granted
only by possession of a valid resource-scoped sharing link.

### QR guest requirements

- **Default: allow QR guest access.** In the opt-in authenticated system, a
  valid secure QR link allows anonymous viewing of its particular shared
  resource and approved PDF delivery only. It does not grant Reader access to
  the library or permission to edit, upload, or generate/regenerate content.
- **Restrict: require sign-in.** An administrator can disable QR guest access;
  QR visitors then require an authenticated Reader, Contributor, or Admin with
  permission to view the resource. There is no shared "Reader" password.
- Apply the current setting on every shared-page, PDF, preview, and download
  request, not just when creating a QR code. Disabling guest access must also
  restrict previously printed secure links and direct file URLs. Previously
  downloaded files cannot be recalled.
- After sign-in, return to the intended resource using a validated local
  destination; do not permit arbitrary redirect URLs. Re-enabling guest access
  must not revive revoked sharing credentials.
- The FORGE Reprint page should explain the active access mode and that the
  administrator may change it later. Keep this notice off the printed copy.
- Test both modes, role permissions, direct endpoint access, cross-resource
  attempts, revocation, cache behavior, and setting changes on existing links.
  Explicitly decide migration of today's numeric links; never treat guessing a
  resource ID as possession of a secure sharing credential.

This implementation is pending owner review and release validation. External proxy
authentication may still require sign-in regardless of the application
setting; proxy routing must be reviewed without exposing unrelated endpoints.

The owner's preferred QR experience is access without login for the particular
shared resource. Treat this as deliberate bearer-link sharing, not a general
authentication bypass:

- Use an unguessable, resource-scoped sharing credential; a sequential resource
  ID alone must not grant anonymous access in an authenticated installation.
- When guest access is allowed, anyone possessing or receiving a valid link/QR
  may access its approved content.
  The link does not itself make a private network reachable.
- Authorize every destination, including PDF delivery, previews, originals,
  and generated output. Decide explicitly which variants the share permits.
- Do not expose other games/resources, library browsing, history, settings,
  uploads, administrative actions, credentials, or internal filesystem details.
- Review revocation/rotation, optional expiry, rate limits, caching, logging,
  referrer leakage, and how previously printed QR codes behave after revocation.
- Add a clear notice on the FORGE Reprint page, not on the printed copy,
  explaining that anybody with the QR code or URL can access the shared content.
  Provide a genuine no-share/no-QR print choice; hiding only the QR while leaving
  a public URL is insufficient. Explain that downloaded copies cannot be revoked.
- Test cross-resource access attempts and every anonymous endpoint before
  enabling this model. Existing numeric `/r/` links are not evidence that secure
  sharing or authentication is already implemented.

The reprint page now describes the active policy. Admins deliberately create
secure shared reprints; ordinary numeric links require sign-in after activation.
The original PDF is the no-FORGE-QR alternative. Further authentication or upload
work still requires owner review; no public-exposure readiness is claimed.

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
