# Self-hosted beta deployment

This guide installs Forge GameSheets from GitHub on a Docker host. The example
location, `/opt/forge-gamesheets`, is a recommendation rather than a
requirement. Use any location that the Docker operator can manage safely.

Forge GameSheets is beta software. Back up both the PDF library and application
data before upgrades. Local accounts are optional and remain off until explicit
operator setup. Forge must not be exposed directly to the public internet or an
untrusted network. See [Accounts and QR sharing](ACCOUNTS.md).

## Requirements

- A Linux, macOS, or Windows host with Docker and Docker Compose v2
- Git for installation and updates
- A readable directory containing the source PDF library
- A separate writable directory for Forge application data
- Enough free space for previews and generated FORGE Reprints
- A current browser with PDF viewing and printing support

Check the required commands:

```sh
docker --version
docker compose version
git --version
```

## Choose storage locations

Forge uses two persistent host directories:

- **Library:** authoritative PDFs and detected game artwork. It is mounted
  read-only inside the container.
- **Data:** the SQLite database, uploaded artwork, previews, and generated
  FORGE Reprints. It is mounted read-write.

The default locations are `library/` and `data/` inside the checkout. External
locations are supported and are preferable when an existing library or backup
policy already exists.

A library on NFS, SMB, or a NAS is supported only when the host operating system
has already mounted it as a normal directory. Forge and its Compose file do not
mount or authenticate to network storage themselves. Confirm that the mount is
available before starting Forge and after every host reboot.

Never use the same directory for both library and data.

## Install the application

Clone the repository:

```sh
sudo mkdir -p /opt/forge-gamesheets
sudo chown "$(id -u):$(id -g)" /opt/forge-gamesheets

git clone \
  https://github.com/natsteff/forge-gamesheets.git \
  /opt/forge-gamesheets

cd /opt/forge-gamesheets
```

Create a local configuration file and the default storage directories:

```sh
cp .env.example .env
mkdir -p data library
sudo chown -R 10001:10001 data
```

The fixed `10001:10001` identity is the non-root account used inside the
container. Do not give that account ownership of the source library. The source
library only needs to be readable and searchable by the container.

## Configure Forge

Edit `.env`; do not edit `compose.yml` for host-specific settings. A future Git
update may need to replace the tracked Compose file, while `.env` is ignored by
Git and remains local to the installation.

```ini
FORGE_GAMESHEETS_BIND_ADDRESS=127.0.0.1
FORGE_GAMESHEETS_PORT=8000
FORGE_GAMESHEETS_BASE_URL=
FORGE_GAMESHEETS_DATA_PATH=./data
FORGE_GAMESHEETS_LIBRARY_PATH=./library
FORGE_GAMESHEETS_IMAGE_TAG=main
FORGE_GAMESHEETS_VERSION=development
FORGE_GAMESHEETS_REVISION=
FORGE_GAMESHEETS_BUILD_DATE=
```

Host paths may be absolute:

```ini
FORGE_GAMESHEETS_DATA_PATH=/srv/forge-gamesheets/data
FORGE_GAMESHEETS_LIBRARY_PATH=/mnt/tabletop/game-sheets
```

Create the configured data directory and make it writable by `10001:10001`
before starting Forge. Preserve the existing ownership of the library.

### Select an access model

| Model | Bind address | Appropriate use |
| --- | --- | --- |
| Localhost only | `127.0.0.1` | Browser or reverse proxy on the Docker host |
| Trusted private LAN | `0.0.0.0` | Trusted household or isolated test network |
| Authenticated proxy or VPN | Usually `127.0.0.1` | Remote access protected outside Forge |

Forge supports opt-in accounts, roles, and login throttling, but has no built-in
TLS or general per-client traffic limit. Non-local sign-in requires HTTPS through
a correctly configured proxy. Binding to `0.0.0.0` exposes the port on every
host interface allowed by the firewall. Use it only on a trusted private LAN.
Do not forward that port from an internet router.

### Configure FORGE Reprint links

`FORGE_GAMESHEETS_BASE_URL` is the address encoded in generated QR codes. It
must be reachable by the phone, tablet, or computer that scans them. Examples:

```ini
FORGE_GAMESHEETS_BASE_URL=http://192.168.1.50:8000
```

```ini
FORGE_GAMESHEETS_BASE_URL=http://forge.home.arpa:8000
```

Use HTTPS when an authenticated HTTPS proxy provides access. Changing this
address makes existing generated copies stale; generate them again so their QR
codes use the new destination.

## Pull and start the published image

The recommended Docker-host workflow pulls the image published from GitHub:

```sh
docker compose pull
docker compose up -d
```

Check startup and health:

```sh
docker compose ps

curl --retry 10 \
  --retry-all-errors \
  --retry-delay 1 \
  http://127.0.0.1:8000/health
```

The health response and the bottom of Settings show the image's release,
revision, and build date.

Set `FORGE_GAMESHEETS_IMAGE_TAG=main` for the current development image. Use a
version tag for a fixed release when one is available.

### Local development build

A developer working from checked-out source can build locally instead:

```sh
./scripts/build
docker compose up -d
```

## Add and organize the library

Each first-level directory under the configured library path represents one
game. PDFs may be nested below it:

```text
game-sheets/
├── Farkle/
│   ├── Farkle - Rules.pdf
│   └── Farkle - Score Sheet.pdf
└── Yahtzee/
    └── variants/
        └── Yahtzee - Score Sheet Large Print.pdf
```

Start Forge after copying files, or select **Rescan library**. Files with
unrecognized names remain accessible and can receive display-title and document
type overrides in the interface. Forge does not rename or modify source PDFs.

Normal operation consists of adding or removing library files, rescanning,
editing display metadata, organizing categories, and optionally generating
FORGE Reprints. Keep the host-mounted library available whenever Forge runs.

## Stop and restart

```sh
docker compose down
```

```sh
docker compose up -d
```

Stopping containers does not remove the host-mounted library or data. Do not
use commands that delete Docker volumes or manually delete the configured data
directory.

## Back up

Back up both configured directories. The library preserves source content; the
data directory preserves metadata, preferences, categories, favorites, pins,
history, uploaded artwork, and generated output.

For a consistent filesystem backup:

Stop Forge using the method appropriate to the deployment, then back up both
configured persistent locations: the source library and the complete
application data directory. Ensure the backup process can read container-owned
files, treat any permission error or omitted path as a failed backup, and verify
the result before restarting. Keep at least one verified copy on separate
storage.

See [Backup and recovery](BACKUP_AND_RECOVERY.md) for restoration guidance.

## Update an existing installation

Do not store server-specific changes in tracked files such as `compose.yml`.
Move them to `.env` before updating.

```sh
cd /opt/forge-gamesheets

git status --short --branch
docker compose down
```

Back up the data directory while Forge is stopped, then update the deployment
files and pull the published image:

```sh
git pull --ff-only origin main
docker compose pull
docker compose up -d --force-recreate

curl --retry 10 \
  --retry-all-errors \
  --retry-delay 1 \
  http://127.0.0.1:8000/health
```

Verify the reported revision, open Settings, inspect one game, view one original
PDF, and open one FORGE Reprint after every update. Database migrations run
automatically; the stopped data backup is the recovery point if an update must
be abandoned.

## Troubleshooting

### Data directory is not writable

Symptoms include permission errors in `docker compose logs app` or a container
that exits during startup. Stop Forge, then apply the container identity to the
configured data directory only:

```sh
docker compose down
sudo chown -R 10001:10001 /actual/path/to/forge-data
```

Do not run that command against the library, repository root, home directory,
or another broad path.

### Port is already in use

Check whether another service is listening on the configured port:

```sh
sudo ss -ltnp | grep ':8000'
```

Choose an unused `FORGE_GAMESHEETS_PORT` in `.env`, rebuild only when other
build settings changed, and recreate the container.

### Forge works locally but not from another device

Confirm `FORGE_GAMESHEETS_BIND_ADDRESS=0.0.0.0` is intentional for this trusted
LAN, the host firewall allows the configured port, and the client uses the
Docker host's LAN address rather than `127.0.0.1`. Confirm the hostname resolves
on the client or use the LAN IP address.

### Games or PDFs are missing

1. Run `docker compose config` and inspect the host source mounted at `/library`.
2. Confirm that source exists, is mounted, and is readable by Docker.
3. Confirm every game is a first-level directory beneath the library root.
4. Select **Rescan library** and review any scan warning shown by Forge.
5. Check `docker compose logs app` for permission and parsing errors.

An unavailable NAS mount may look like an empty directory. Restore the host
mount before rescanning so temporary storage failure is not mistaken for an
intentional library change.

### Container exits immediately

Inspect its status, fully rendered configuration, and logs:

```sh
docker compose ps -a
docker compose config
docker compose logs --tail=200 app
```

Common causes are a missing bind-mount path, an unwritable data directory, an
unreadable library, or an invalid `FORGE_GAMESHEETS_BASE_URL`.

### Health briefly returns an empty response

The application may still be initializing. Use the documented retry command
instead of treating the first response immediately after startup as a failure.
If the container never becomes healthy, inspect its logs.

### A pull is blocked by local Compose changes

Do not discard the changes without reviewing them. Run:

```sh
git diff -- compose.yml
```

Move the corresponding bind address, port, base URL, data path, or library path
into `.env`. Preserve a copy of the diff, restore only `compose.yml`, and then
retry the fast-forward pull.

## Security and content responsibility

- Keep Forge on localhost or a trusted private network unless an authenticated
  proxy or VPN protects it.
- Keep the source library read-only inside the container.
- Do not place credentials in the repository or `compose.yml`.
- Back up application data before every update.
- Keep Docker, the host operating system, and any proxy updated.
- Treat QR links as direct navigation to resources on the operator's server.
- Store and print only content the library operator is authorized to use.

For beta workflow testing, continue with [the beta testing guide](BETA_TESTING.md).

## Browser submission protection

FORGE rejects state-changing requests unless their Origin matches the requested
scheme, hostname, and port. If Origin is absent, a matching Referer is required;
missing or invalid values receive 403. This protects browser submissions, not
access by untrusted clients, and does not replace authentication.

Reverse proxies must preserve the public Host and convey the external scheme
through the server's trusted-proxy configuration. Do not trust forwarded headers
from arbitrary clients. FORGE does not use raw X-Forwarded-Host as an allowlist.
The QR base URL is not an alternate allowed origin. Use the same address to open
the form and submit it. Scripted mutations must supply their intended Origin.
Referrer information is retained for same-origin requests only and is not sent
to other origins. GET-based viewing and QR navigation remain available without
Origin headers; protections for expensive GET operations are a separate review.

Viewing and downloading an existing FORGE Reprint never creates a missing
generated file. Generate or regenerate it from its FORGE Reprint page first.
Original PDF view/download intentionally records Recent and History activity.
Preview requests may populate their bounded cache; both are expected product
behavior rather than administrative changes.

FORGE accepts `localhost`, `127.0.0.1`, `::1`, and the hostname from
`FORGE_GAMESHEETS_BASE_URL` automatically. Add other exact LAN or proxy names as
a comma-separated `FORGE_GAMESHEETS_ALLOWED_HOSTS` value in `.env`, without
schemes, ports, paths, or wildcard characters. For example:

```dotenv
FORGE_GAMESHEETS_ALLOWED_HOSTS=docker-test.nate,192.168.1.7
```

Requests using any other or malformed Host header are rejected. This is
defense-in-depth against unexpected hostnames; it is not authentication and
does not make direct Internet exposure appropriate.

## Request limits, proxy trust, and logs

Artwork still has a 25 MiB file limit. All mutating requests are capped at
26 MiB including multipart overhead, before form parsing, even without a
Content-Length header. Receiving a request has a 30-second timeout and four
concurrent submissions are admitted per application process. Oversized requests
receive 413, timed-out reception 408, and a busy server 503 with Retry-After.
These ingress limits are separate from the PDF budgets below.
Protected proxies should also impose suitable ingress limits and timeouts.

When using an HTTPS reverse proxy, set
`FORGE_GAMESHEETS_FORWARDED_ALLOW_IPS` to the actual proxy IP or trusted network
as seen by the container. The default `127.0.0.1` does not trust arbitrary LAN
clients. Do not set `*` for normal LAN deployment. The proxy must replace client
forwarded headers, preserve the public Host, and prevent direct access around
its authentication. This controls trusted scheme/client forwarding separately
from FORGE's allowed Host list. See [Uvicorn proxy settings](https://www.uvicorn.org/settings/).
End-to-end HTTPS/proxy verification remains deployment-specific.

Uvicorn access/error logs remain available through Docker. Compose uses rotating
local logs (10 MB per file, three files) to bound ordinary log growth. Access
logs can contain client addresses and requested URLs; protect log access and
avoid putting secrets in URLs. No new body, token, or form-value logging is
introduced. These operational logs are not a user-attributed security audit
trail. Account and sharing operations have a bounded, user-attributed security
event list when accounts are enabled; it is not a comprehensive content audit.
Redact `/s/` sharing credentials in proxy logs, including encoded login return
paths. Application access logs redact these links, but cannot control proxy logs.

### PDF rendering and derived storage

One preview/reprint render runs at a time per process, with an additional
advisory file lock preventing concurrent renders by workers sharing the data
directory. Admission waits at most five seconds in-process; a busy worker lock
rejects immediately. `.pdf-processing.lock` is a persistent coordination file,
not a generated PDF; do not delete it while FORGE is running. The supported
Mac/Linux filesystem must provide reliable advisory file locking.

New output writes are capped at 250 MiB per reprint and 1 MiB per preview. The
combined `generated/` and `previews/` budget is 5 GiB, including temporary and
older files. Before rendering, FORGE conservatively requires room for the full
per-file maximum plus 100 MiB free disk headroom; old output stays in place
until a replacement passes validation. This means even a small reprint requires
350 MiB free disk and 250 MiB remaining cache budget to begin. Space is checked
again before publishing. No files are automatically evicted to meet these caps.

Limit or write failures remove the operation's partial output and preserve
original PDFs and previous reprints. The reprint page reports failure even when
an older copy is still available. Existing copies can still be viewed/downloaded.
These are application safeguards, not a filesystem quota: other applications,
uploads, and databases can consume space between checks. Use host quotas and
capacity monitoring for a hard deployment-wide guarantee. These checks do not
provide a killable native-parser timeout or a per-client rate limit.
