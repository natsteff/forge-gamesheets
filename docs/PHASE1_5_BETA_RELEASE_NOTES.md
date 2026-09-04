# Forge GameSheets Phase 1.5 beta

Forge GameSheets is a private, self-hosted library for organizing and using
printable game resources. Phase 1.5 adds the first generated-document workflow:
FORGE Reprint creates a separate printable copy of an existing PDF with a small
Forge footer and QR link back to the resource.

This is a prerelease for wider testing. Source PDFs remain authoritative and
are never modified by the Reprint workflow.

## Highlights

### FORGE Reprint

- Creates a separate derived PDF while preserving the original source file
- Adds a compact Forge logo, return URL, responsibility notice, and QR code
- Uses stable resource links that survive display-title changes
- Provides deliberate View, Download, and Regenerate actions
- Confirms successful regeneration in the interface
- Keeps generated output available across application restarts
- Rebuilds outdated output when the generator or QR destination changes
- Includes print guidance for keeping the complete footer inside the printable
  area

Generated copies created by earlier development versions may require a one-time
regeneration so they receive the current footer design.

### Self-hosted deployment

- Runs as a deterministic non-root container identity
- Keeps the source library mounted read-only and application data separate
- Preserves localhost-only access as the safe default
- Makes the bind address, port, base URL, data path, and library path
  configurable through `.env`
- Reports version, revision, and build date in Settings and `/health`
- Includes detailed deployment, upgrade, backup, troubleshooting, and security
  guidance

### Library and interface improvements

- Adds a Categories navigation view and flat All Games view
- Supports multiple customizable categories per game
- Adds configurable library footer text and Recent-item limit
- Places FORGE Reprint first among resource actions while retaining original
  PDF access from the Reprint page
- Prevents stale browser artwork and preview images after moving between
  installations or rebuilding application data
- Adds public screenshots based entirely on fictional demonstration content

## Security and access

Current source includes opt-in local Admin, Contributor, and Reader accounts;
activation requires local Admin setup. Existing installations remain in
trusted-operator mode until activated. The supplied configuration listens only
on localhost by default. See [accounts and QR sharing](ACCOUNTS.md).

Do not expose Forge directly to the public internet or an untrusted network.
Use trusted-LAN access only when appropriate, or place Forge behind an
authenticated proxy, VPN, or other intentionally configured access-control
layer.

The library operator controls the source files and is responsible for ensuring
their storage, use, reproduction, printing, and distribution are authorized.
The FORGE GAMESHEETS mark identifies the software used to prepare a copy; it
does not claim ownership, affiliation, or permission for the source content.

## Upgrade notes

Before updating, stop Forge using the method appropriate to the deployment and
back up both configured persistent locations: the source library and the
complete application data directory. Ensure the backup can read
container-owned files and completes without omitted paths or permission errors.

Preserve the installation's `.env`, pull the new code, rebuild the image with
the desired build identity, and verify `/health` and Settings afterward. See
the [deployment guide](deployment.md) for the supported workflow.

## Known limitations

- Printing remains browser-managed; Forge cannot reliably confirm that a
  physical print completed.
- PDF previews show only the first page and may be unavailable for malformed or
  unsupported files.
- FORGE Reprint adds a footer but does not edit, combine, or redesign source
  content.
- Existing generator versions are not batch-regenerated during an upgrade;
  affected Reprints are recreated on demand.
- Game folders must currently be first-level children of the library root.
- BoardGameGeek enrichment and the future FGS structured GameSheet system are
  not included in this release.
- Remote synchronization, hosted content, cloud backup, and built-in
  authentication are not included.

## Feedback requested

Testing is especially useful for:

- installation and upgrade clarity;
- library permissions and mounted-storage behavior;
- PDF compatibility, page orientation, and print scaling;
- footer and QR readability on color and black-and-white printers;
- QR access from phones and tablets on a trusted LAN;
- persistence of categories, metadata, preferences, shortcuts, and generated
  output;
- clear error handling without modification of source files.

Follow the [beta testing guide](BETA_TESTING.md) and report defects through
[GitHub Issues](https://github.com/natsteff/forge-gamesheets/issues). Do not
attach copyrighted PDFs, private library data, credentials, or publicly
reachable private-library links to a report.
