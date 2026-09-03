# Self-hosted beta deployment

This guide installs Forge GameSheets from GitHub on a Docker host. The example
location, `/opt/forge-gamesheets`, is a recommendation rather than a
requirement. Use any location that the Docker operator can manage safely.

Forge GameSheets is beta software. Back up both the PDF library and application
data before upgrades. Forge has no built-in authentication and must not be
exposed directly to the public internet or an untrusted network.

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

Forge has no user accounts, authentication, authorization, rate limiting, or
built-in TLS. Binding to `0.0.0.0` makes the configured port available on every
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

## Build and start

Build the image. The project command automatically embeds the checked-out Git
revision and UTC build date:

```sh
./scripts/build

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

The health response and the bottom of Settings show the running release,
revision, and build date. The revision should match:

```sh
git rev-parse --short HEAD
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

Back up the data directory while Forge is stopped, then update and rebuild:

```sh
git pull --ff-only origin main

./scripts/build

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
