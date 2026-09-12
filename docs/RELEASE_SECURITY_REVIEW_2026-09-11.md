# Release security review — September 11, 2026

## Review record

- Candidate commit: `d67cbb2ca341a4ef241829e167aca12166ff60e6`
- Review type: maintainer-led, AI-assisted security self-assessment
- Deployment model: self-hosted localhost, trusted private LAN, or protected
  reverse proxy/VPN; no direct public-Internet exposure
- Result: no release-blocking finding identified
- Assurance boundary: this is not an independent audit, penetration test, or
  certification

## Evidence reviewed

- Explicit fail-closed route inventory for public, Reader, Contributor, and Admin
  access
- Session creation, expiry, rotation, invalidation, secure-cookie behavior,
  password confirmation, and login throttling
- Same-origin mutation checks, Host validation, request-body limits, path
  resolution, generated-file containment, and processing budgets
- Public-by-default and per-resource restricted QR landing/original/reprint paths
- Non-root, read-only container configuration with dropped capabilities,
  `no-new-privileges`, PID/memory/CPU limits, bounded logs, read-only library,
  and separate writable data
- Repository scan for tracked databases, PDFs, environment files, credentials,
  private keys, and generated output
- GitHub workflow run 34656194184 for `d67cbb2`: tests, Ruff, Python dependency
  audit, runtime-image build, container vulnerability reporting, fixed-critical
  blocking scan, and publication all completed successfully
- Focused local security suite: 362 tests passed
- Full suite previously recorded for the same source: 637 passed, 1 skipped

## Accepted boundaries and future hardening

### Stable public QR addresses

Unrestricted QR resources use stable numeric `/r/{resource-id}` addresses. They
are intentionally public to anyone who can reach the server and are enumerable;
they are not secret sharing tokens. Each address exposes only its resource page,
original PDF, and existing generated copy. An Admin can require sign-in for an
individual resource, including a previously printed QR code. This deliberate
home-hosted usability choice depends on the documented trusted-network boundary.

### Native document parsing

PDF and image parsing remains in the application process. Existing file, page,
output, scratch-space, concurrency, duration, and derived-storage limits reduce
risk but do not provide killable process isolation for malformed native-parser
input. Only trusted content should be added. Parser subprocess isolation and a
per-client traffic policy remain future hardening because they would materially
increase complexity for the current beta.

### Dependency reproducibility

Published builds audit resolved Python dependencies and scan the exact runtime
image. Dependency ranges are not yet locked, the Python base image is not pinned
by digest, and GitHub Actions use version tags rather than immutable commit SHAs.
A lock/update policy, digest-pinned base image, and immutable Action references
remain future supply-chain hardening. Green scans do not make builds fully
reproducible or prove that no vulnerability exists.

## Disposition

The reviewed controls and successful clean-install validation support continued
trusted-network beta testing. The accepted boundaries above do not support direct
public-Internet exposure. Reassess changed trust boundaries, authentication,
uploads, parser execution, and dependency controls before a major release.
