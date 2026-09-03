# Security priorities and future access/upload planning

Security is a primary release requirement. This document records future work,
not implemented protections or approval to begin login or upload development.
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

Reference: [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/).

## Future login, roles, and QR sharing — review with owner first

Before implementation, revisit this plan with the owner and obtain explicit
approval for access models, role boundaries, and deployment scope. Reader,
librarian, and administrator are candidate roles, not a final design.

The owner's preferred QR experience is access without login for the particular
shared resource. Treat this as deliberate bearer-link sharing, not a general
authentication bypass:

- Use an unguessable, resource-scoped sharing credential; a sequential resource
  ID alone must not grant anonymous access in an authenticated installation.
- Anyone possessing or receiving the link/QR may access its approved content.
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

The notice and print-choice requirements belong to this future access work;
this planning update does not change the current interface or link behavior.

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
