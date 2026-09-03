# Initial ASVS security self-assessment

Date: 2026-09-03. Reviewer: Codex, primary development agent.
Baseline: `bec06021e4d5dbdca93ddde0217b310538f6c8d0`, plus the uncommitted
README, security-plan/agent-guidance, timezone-help, Recent-help, and associated
test changes present during review. This is not a tagged release assessment.

## Scope and conclusion

This is an initial, selected-control assessment using OWASP ASVS 5.0.0, not a
complete requirement-by-requirement verification or an ASVS level certification.
Source/configuration inspection and isolated FastAPI TestClient probes found
actionable browser-origin and resource-control gaps. No application fixes were
made. No live installation, real library, credentials, or external BGG requests
were used in probes. Docker Test was not touched.

Supported assumption: all direct application users are trusted operators, with
localhost/LAN or a separately secured access layer. There are no built-in
accounts or roles. A reader-only or public QR boundary does not currently exist.
An authenticated proxy is not by itself a substitute for CSRF protection.

## Findings and recommended order

Severity is provisional and depends on reachability and attacker capabilities;
these are not CVSS scores. Fixes require a separate implementation decision.

### A1 — Cross-site state changes accepted (medium; first priority)

Follow-up (uncommitted): all unsafe HTTP methods now require a matching Origin,
or matching Referer only when Origin is absent, before body parsing. Missing,
null, duplicate, malformed, cross-origin and cross-site submissions fail closed.
The original Settings probe now returns 403. This is not authentication and does
not resolve DNS rebinding/Host validation (A4). GET-triggered generation and use
recording remain a separate open item; the complete A1 scope is not closed.

- Evidence: `app/web.py:275` and other POST routes accept form submissions;
  `app/main.py` installs no anti-forgery middleware. An isolated POST to
  `/settings/preferences` with `Origin: https://untrusted.example` and
  `Sec-Fetch-Site: cross-site` returned 303 and persisted the supplied footer
  and recent limit without credentials or a token.
- Impact: a browser able to reach FORGE may be induced to change settings or
  invoke other state-changing operations. Browser private-network policies and
  proxy configuration affect exploitability; an actual browser exploit was not
  tested. Lack of permissive CORS does not itself reject ordinary form posts.
- Recommendation: consistent server-side anti-forgery controls on mutations,
  with trusted-origin/proxy configuration and negative regression tests.
  Separately review GET-triggered generation and usage recording in
  `_generated_reprint_response` and `_resource_response`.
- Mapping: v5.0.0-3.5.1 and v5.0.0-3.5.3 (gap).

### A2 — Processing and ingress limits incomplete (medium)

Follow-up (uncommitted): preview and reprint processing now enforce a 250 MB
source limit, 500-page limit, and 200-inch maximum page dimension. Preview
rasterization is capped at 25 million pixels. Artwork processing checks the
existing 25 MB byte limit and a new 40-megapixel limit before decoding pixels.
Limit failures do not publish a derived file. Multipart request parsing still
occurs before the application-level artwork byte check, and process isolation,
timeouts/concurrency controls, deployment resource limits, and empirical limit
validation remain open. A2 is therefore reduced, not closed.

- Evidence: `app/library/previews.py:41` renders at a fixed 1.5 scale before
  resizing, without a page-dimension/pixel budget. `app/library/reprints.py`
  processes all pages without upper page count, input size, or execution budget.
  Both run in the application process. Compose declares no memory/CPU/PID limits.
- Artwork is already uploadable: `app/web.py:655` reads at most 25 MB plus one
  byte, but this happens after multipart parsing. No application-wide incoming
  request-size budget was found. Multipart spooling and limits depend on the
  installed Starlette version and proxy; the 25 MB check does not establish a
  transport-level cap. Pillow has decompression-bomb protection, but no explicit
  application-specific pixel limit is enforced before `image.load()`.
- Impact: expensive source documents or upload requests can consume shared
  memory, processing time, temporary storage, or application data capacity.
- Recommendation: bounded ingress and pixel/page/file budgets, concurrency
  control, isolated/timeout-bounded rendering, and deployment resource limits.
  Decide limits from representative documents before implementing them.
- Mapping: v5.0.0-5.2.1 and v5.0.0-5.2.6 (partial/gap).
- Validation: static evidence only; no oversized files, load test, or deliberate
  resource-exhaustion attack was run.

### A3 — Browser defense headers absent (low to medium)

Follow-up (2026-09-03, uncommitted): XSS defense-in-depth added in
`app/security.py`, with escaping regression tests for stored metadata and
reflected search text. Library responses now enforce CSP (no inline scripts,
no eval, same-origin assets, no objects/base overrides/framing), nosniff, and
no-referrer. Original PDF disposition is preserved. Framework-generated
`/docs`, `/redoc`, and `/docs/oauth2-redirect` retain their existing asset policy
and are explicitly excluded from CSP, not from nosniff/referrer protection.
Unhandled server-error response coverage and real-browser/mobile PDF behavior
still need verification. This does not fix A1 (CSRF) or A4 (Host validation),
and no exploitable XSS was demonstrated in the original text-rendering paths.

- Evidence: `/settings` returned no CSP, nosniff, Referrer-Policy, or
  X-Frame-Options header in the isolated app; no equivalent frame restriction
  was identified. Proxy-injected headers were not assessed.
- Impact: missing defense against framing/clickjacking and weaker containment
  if an injection defect occurs. This is not proof of an existing XSS exploit.
- Recommendation: tested CSP including framing restrictions, nosniff and
  referrer policy, preserving intentional PDF viewing. Apply HTTPS/HSTS at the
  appropriate secured deployment boundary, not blindly to localhost HTTP.
- Mapping: v5.0.0-3.4.3 through 3.4.6 (gap in application responses).

### A4 — Host boundary not enforced (medium, conditional)

Follow-up (uncommitted): exact Host validation now allows loopback names, the
configured QR base hostname, and explicitly configured additional hostnames/IP
addresses. Patterns, ports in configuration, credentials, malformed/duplicate
Host values, and unrecognized names are rejected before routing. Regression
tests cover DNS suffix confusion and LAN/base-URL access. This is
defense-in-depth, not authentication; trusted-proxy behavior still requires
deployment validation.

- Evidence: `/settings` with `Host: untrusted.example` returned 200 and produced
  absolute links using that host. No trusted-host middleware is configured.
- Impact: weakens protection against unexpected hostnames and DNS-rebinding
  scenarios. A complete rebinding exploit was not tested. QR targets use the
  configured base URL, so QR poisoning was not demonstrated.
- Recommendation: configurable allowed hosts and documented trusted proxy
  behavior, with tests for rejected hosts and legitimate localhost/LAN access.
- Mapping: ASVS V13 configuration review; additional requirement-level mapping
  remains open. Do not report a proven data-exfiltration exploit.

### A5 — BGG client representation includes token (low, latent)

Follow-up (uncommitted): the BGG client token is excluded from its dataclass
representation and a synthetic-secret regression test protects that behavior.
No BGG rollout or real-token test was performed.

- Evidence: `app/bgg/client.py:63` is a dataclass token field without
  `repr=False`. A synthetic-token probe confirmed it appears in `repr(client)`.
  `Settings.bgg_api_token` already uses `repr=False`.
- Impact: potential exposure if the client object is logged/debugged. No actual
  token leak or current logging of this object was observed.
- Recommendation: redact the field and add a synthetic-secret regression test.
  Keep BGG disabled pending approval; this does not authorize feature rollout.
- Mapping: ASVS V14/V16 secret-handling review, partial coverage.

### A6 — Release security assurance gaps (process, not proven exploit)

Follow-up (uncommitted): Compose now uses a read-only root filesystem, drops all
Linux capabilities, prevents privilege escalation, applies PID/CPU/memory
limits, supplies a bounded temporary filesystem, and uses an init process. The
existing `/data` mount remains writable and `/library` remains read-only. These
settings require Mac and Linux runtime verification; pipeline scanning and
dependency pinning remain open.

- `.github/workflows/publish-container.yml` builds/pushes without a test or
  vulnerability-scan gate in that workflow. External branch protection/checks
  were not inspected. Dependencies have broad ranges; the base image and action
  references are mutable tags. No resolved dependency/image inventory was audited.
- Docker runs non-root and mounts the source library read-only, which are useful
  controls. The app owns `/app`; root filesystem read-only, capability reduction,
  and no-new-privileges are not explicitly configured in Compose.
- No `.dockerignore` exists. Dockerfile COPY instructions are selective, so this
  is not evidence that local credentials or PDFs are in the published image.
  Consider build-context exclusions as preventive hygiene.
- Recommendation: test publication gates, resolved dependency/image scanning,
  repeatable dependency policy, and proportionate container hardening. Review
  a private vulnerability-reporting channel before broader release.
- Mapping: ASVS V13/V15; not assessed to a complete control-level pass/fail.

## Positive evidence and boundaries

| Area | Evidence and status |
| --- | --- |
| Source paths | `resolve_resource_pdf` rejects absolute/traversal/symlink paths; existing file tests pass. Positive evidence, not proof against filesystem races. |
| Generated storage | Generated-directory escape test passes; file-level symlink/race behavior needs deeper review. |
| Text rendering | A stored script-shaped footer renders escaped, not as a raw script. Default Jinja template rendering and JS `textContent` use inspected. Not every field/context was fuzzed. |
| SQL | Inspected search code binds input and uses constant SQL fragments; no SQL injection found in that path. Full query-by-query audit remains open. |
| Downloads | Filename sanitization removes control/path characters; FileResponse sets disposition and PDF media type, and responses use no-store. Original PDF content is not malware-scanned. |
| Optional BGG | Fixed HTTPS API root, timeout, bounded response read, translated errors and hidden Settings secret. Redirect authorization forwarding/XML adversarial tests remain open. |
| Filesystem/container | Separate data/library validation, read-only source mount, UID 10001 runtime. Runtime container enforcement was not inspected this turn. |

No antivirus check is implemented: v5.0.0-5.4.3 is unmet for untrusted files,
not silently passed because automatic scanning is currently deferred. This
requires documented scope/risk treatment if targeting ASVS L2. An upload warning
or external scanning link is not equivalent to enforcing the control.

Authentication/session, JWT, OAuth/OIDC, and WebRTC implementation controls are
not applicable to absent features; access-control requirements are not thereby
satisfied for public or multi-role hosting. TLS and operator access controls
remain deployment-dependent and untested. Cryptography, full logging/error
coverage, data retention, dependency CVEs, native parser vulnerabilities, and
all remaining ASVS requirements are unassessed in this initial pass.

## Verification record

- Focused existing tests (files, generated paths, config, web, BGG client):
  **104 passed**.
- Host suite: **192 passed, 1 deselected**, seven dependency deprecation warnings.
  The known case-insensitive-filesystem scanner test was excluded on macOS;
  Linux/container suite was not rerun.
- Ruff: passed. Documentation whitespace check: passed.
- Disposable probe: foreign-origin POST 303, changed value persisted; arbitrary
  Host GET 200 and host reflected in links; listed headers absent; script footer
  escaped. Synthetic client token appears in representation.
- Probe script used temporary directories and TestClient, not a running server.
  It remains locally at `/tmp/forge_asvs_probe.py` and is not a shipped test.
  Reproduction: create an empty temporary library/data app, submit the form
  fields `footer_text`, `recent_limit`, `timezone_name` to the preferences route
  with the headers in A1, then read preferences from that temporary database.

## Next decision

Review A1–A6 with the owner before implementing fixes. Prioritize A1, then bounded
processing and host/browser protections. Do not interpret a green functional
test suite as evidence that these security gaps are resolved. The independent
review reminder was delivered during this assessment; no second reviewer ran.

Complete a requirement-level inventory and remaining dynamic/dependency/runtime
checks before claiming a full ASVS assessment or releasing against that claim.

## Standards references

- [OWASP ASVS overview and stable version](https://owasp.org/www-project-application-security-verification-standard/)
- [ASVS 5.0.0 web frontend requirements](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md)
- [ASVS 5.0.0 file handling requirements](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x14-V5-File-Handling.md)
- [ASVS 5.0.0 configuration requirements](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x22-V13-Configuration.md)
