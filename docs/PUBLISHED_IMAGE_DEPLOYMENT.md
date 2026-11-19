# Install and maintain a published Docker image

This path needs Docker Engine and Docker Compose v2 or a compatible container
manager, two host directories, and one downloaded `compose.yml`. Git, a local
build, and an external `.env` file are not required. The existing root
`compose.yml`, `.env.example`, and development workflow remain supported.

The deployment file is [deploy/compose.yml](../deploy/compose.yml).
[deploy/.env.example](../deploy/.env.example) is an optional convenience;
defaults are embedded in the Compose file. It uses the same image and
configuration variables as the root Compose file, without its build section.
Changing deployment paths does not change the FGS format or database schema.

## Choose access before deploying

The new deployment file defaults to owner-account protection:

```yaml
environment:
  FORGE_GAMESHEETS_ACCESS_MODE: owner
```

`owner` requires browser first-owner setup and sign-in. Remote setup/sign-in
requires HTTPS through a trusted reverse proxy; localhost HTTP remains supported.

For intentional account-free access on a trusted LAN, change that one entry to:

```yaml
environment:
  FORGE_GAMESHEETS_ACCESS_MODE: trusted
```

Keep all the other environment entries and security settings. In `trusted`
mode, anyone who can reach FORGE can browse, edit settings/metadata and remove
shared application content. The source PDF mount remains read-only. LAN HTTP is
supported in this mode; changing access mode does not expose a localhost-only
port automatically. Choose LAN binding separately below.

This setting never disables already-enabled accounts or bypasses local recovery.
If users exist, sign-in stays required even with `trusted` selected. See the
[account and transition rules](ACCOUNTS.md#choose-the-deployment-access-mode).

An optional `.env` can set this variable when the Compose definition forwards it.
Older downloaded Compose files may not contain the new environment entry; add
the entry or deliberately update the configuration as well as the image.
Older application images may ignore unknown environment variables: use the
matching image/configuration release and verify its expected build revision.
A prerelease configuration alone cannot add account protection to an older image.

The root developer Compose file retains an empty compatibility default for an
omitted variable. That preserves open pre-existing installations; fresh data
still defaults to owner setup. Its new-install `.env.example` explicitly selects
`owner`. Existing `.env` files are not rewritten.

## Prepare storage and permissions

Create separate, nonnested host directories before deploying:

| Mount | Container access | Required host access for UID/GID 10001:10001 |
| --- | --- | --- |
| `/data` | Read/write | Read, write and directory traversal |
| `/library` | Read-only | Read files and traverse all parent/game directories |

The image runs as the fixed non-root account `10001:10001`. It does not implement
`PUID`/`PGID` remapping or repair host ownership automatically. Keep the source
library's existing ownership; grant only the necessary read/traverse ACLs.
Do not make the library writable to solve a data-directory permission problem.
Do not run the app as root or use `chmod 777`.

On a fresh Linux installation, with these example locations:

```sh
mkdir -p /opt/forge-gamesheets/data /opt/forge-gamesheets/library
sudo chown 10001:10001 /opt/forge-gamesheets/data
sudo chmod 700 /opt/forge-gamesheets/data
```

Creating directories under `/opt` may require an administrator. These commands
are for fresh directories, not recursive ownership changes to an existing NAS
share. Existing data must remain writable by the runtime account. NAS ACLs,
parent traversal, Docker user-namespace mappings and network-share permissions
must also allow the container's effective identity. Pre-mount network shares on
the host; the application never mounts or authenticates to SMB/NFS itself.

The deployment file refuses to create missing bind sources. A missing directory
is a configuration error, rather than a silently created empty/root-owned folder.
This cannot detect a disconnected NAS mount if its empty mountpoint still exists:
verify the backing mount before startup. Only dummy data should be used to test
permissions. Back up both the library and complete data directory.

## CLI: download one file and start

For a fresh installation, from the directory that should contain `compose.yml`:

```sh
curl --fail --location \
  https://raw.githubusercontent.com/natsteff/forge-gamesheets/main/deploy/compose.yml \
  --output compose.yml
docker compose config --quiet
docker compose pull app
docker compose up -d --no-build app
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

With no overrides, `./data` and `./library` are relative to the saved file and
must already exist. The host port is 8000, bound to localhost only, and the image
is `ghcr.io/natsteff/forge-gamesheets:main`. Health becoming ready can take a few
seconds. Confirm the expected revision in `/health` and Settings.

To customize, edit the downloaded file's default values, set shell variables,
use GUI environment inputs, or optionally save the deployment environment
example beside the file as `.env`. No `env_file:` entry is required.
Use absolute host paths in GUI deployments. An existing shell variable overrides
the corresponding `.env` value. Keep tokens private; resolved configuration and
GUI screenshots can reveal configured secrets.

The `main` tag is a moving beta channel. Select `sha-<revision>` or a published
release tag for a deliberate fixed build. The image is pulled/updated only when
the operator requests it; this setup installs no update agent or schedule.
CPU architecture is selected by Docker from the AMD64/ARM64 image manifest.
Older/unsupported NAS CPUs are not made compatible by this Compose file.

## Trusted-LAN and reverse-proxy access

Network defaults remain localhost-only. The standalone file selects `owner`;
choose `trusted` explicitly for account-free LAN HTTP access. Protected accounts
stay protected in either mode. Remote setup/sign-in require HTTPS. See
[account setup](ACCOUNTS.md).
For explicit trusted-LAN access, for example:

```ini
FORGE_GAMESHEETS_BIND_ADDRESS=0.0.0.0
FORGE_GAMESHEETS_PORT=8000
FORGE_GAMESHEETS_BASE_URL=http://192.0.2.20:8000
```

Replace the documentation address with the Docker host's actual LAN address.
The URL's hostname is allowed automatically; additional exact hostnames/IPs go
in `FORGE_GAMESHEETS_ALLOWED_HOSTS`. Leave proxy trust at its default for direct
LAN access; never set it to `*` merely to fix connectivity.

`0.0.0.0` binds all host interfaces allowed by the firewall. Use it only on a
trusted private network, with no router port forwarding or direct internet
exposure. A remote browser cannot reach a localhost-only NAS binding.
Non-local account sign-in requires HTTPS through a correctly configured trusted
proxy. A proxy in another container may also need an explicitly reachable
upstream; its `127.0.0.1` is not the FORGE container or Docker host.
See the existing [proxy and account configuration](deployment.md#https-with-nginx-proxy-manager)
and [security boundary](ACCOUNTS.md). Do not replace the existing proxy settings
when adopting the deployment-only file.

## GUI installations

The same application contract applies in every manager: published GHCR image,
container port 8000, fixed non-root identity, read-only library, writable data,
and the hardening shown in the Compose file.

### Synology Container Manager

Use **Project** to upload/paste the deployment `compose.yml`. The owner has
successfully installed on Synology with a DSM service-account identity, folder
ACLs, explicit allowed hosts, and the unsupported CPU quota removed. This is
experience from one installation, not a compatibility claim for every NAS.

1. Create a project folder and separate data/library folders. Use absolute bind
   source paths, for example `/volume1/docker/forge-gamesheets/data` and your
   actual PDF share. Do not replace working paths when upgrading.
2. Choose the runtime identity. The image defaults to `10001:10001`; grant it
   data read/write and library read/traverse access. Alternatively, use a
   dedicated non-administrator DSM service account and add `user: "<UID>:<GID>"`
   under `app`, replacing both placeholders with its actual numeric IDs. An
   administrator can obtain them with `id accountname` over SSH. Grant that
   account the required DSM folder ACLs, including parent traversal. This is a
   Compose user override, not `PUID`/`PGID` support. Keep `/library` read-only.
3. Remove `cpus: 2.0` from the imported example on Synology hosts that reject CPU
   quotas/CFS settings. Retain memory, process, and other security settings.
4. Choose `owner` for browser account setup with remote HTTPS, or explicitly
   choose `trusted` for account-free LAN HTTP. Existing accounts remain protected.
   Choose localhost/proxy or LAN port binding separately; configure the actual
   hostname/IP in base URL and allowed hosts. Do not enable a Web Station portal,
   router forwarding, or public exposure automatically.
5. Choose either configuration method below, then apply/build the Project to
   download the published image and create the container. No local image build
   is needed. After changing settings, recreate the container; restarting alone
   does not change its environment. Check health, Settings build information,
   library access, and persistence.

#### Option A: settings directly in YAML

No `.env` file is needed. Merge settings into the existing `app.environment`
block; preserve all other entries, mounts, ports, and security settings:

```yaml
services:
  app:
    environment:
      FORGE_GAMESHEETS_ACCESS_MODE: trusted
      FORGE_GAMESHEETS_BASE_URL: "http://192.0.2.20:8000"
      FORGE_GAMESHEETS_ALLOWED_HOSTS: "192.0.2.20,nas.example.lan"
      FORGE_GAMESHEETS_BGG_API_TOKEN: ""
```

This is a fragment, not a complete project. Replace the example address and
hostname with your NAS values. For direct LAN access, also change the existing
port mapping to `"0.0.0.0:8000:8000"` (or the intended NAS interface/host port).
For `owner`, use the HTTPS proxy configuration described above instead.

#### Option B: optional `.env` beside `compose.yml`

Keep the supplied Compose variable references, such as:

```yaml
FORGE_GAMESHEETS_BGG_API_TOKEN: ${FORGE_GAMESHEETS_BGG_API_TOKEN:-}
```

Save [deploy/.env.example](../deploy/.env.example) as `.env` in the project's
Compose working directory and edit its values. For example, for trusted LAN use:

```dotenv
FORGE_GAMESHEETS_ACCESS_MODE=trusted
FORGE_GAMESHEETS_BIND_ADDRESS=0.0.0.0
FORGE_GAMESHEETS_BASE_URL=http://192.0.2.20:8000
FORGE_GAMESHEETS_ALLOWED_HOSTS=192.0.2.20,nas.example.lan
FORGE_GAMESHEETS_BGG_API_TOKEN=
```

Confirm the uploaded project includes `.env` in that directory; a YAML-only
upload does not transfer it. If the installed manager does not load it, use
Option A. No `env_file:` entry is required: Compose uses `.env` for substitution.
A literal YAML value overrides the corresponding `.env` setting, and an entry
with no reference in Compose is not forwarded automatically. Keep tokens out of
shared YAML, screenshots, support bundles, and version control with either method.

#### Optional BoardGameGeek integration

Synology uses the same BGG integration as other hosts. Follow the
[BGG configuration guidance](BGG_API.md) to obtain
an approved token, then set `FORGE_GAMESHEETS_BGG_API_TOKEN` using either option
above. Leave it blank to run without API integration. Recreate the container
after changing the token and check the integration status in Settings. Do not
share the token or resolved Compose output when troubleshooting.

### Portainer

For a Docker Standalone endpoint, use **Stacks → Add stack → Web editor** or
file upload. Paste/upload the deployment file and set host paths using the
editor or stack environment variables. An external `.env` is not necessary.
Do not add a required `stack.env` file or enable webhooks/automatic updates.
Bind paths refer to the Docker endpoint's host, not the browser or Portainer
container. Docker Swarm is outside this deployment recipe.

### Unraid

The native container template UI is not assumed to import Compose. For a
Compose-capable setup, use the same deployment file. For the native UI, map the
GHCR repository, port, `/data`, `/library`, environment variables, health check,
and security/resource settings from the Compose definition.

Use bridge networking and preserve the chosen host bind address. Set the library
mapping read-only, grant data access to `10001:10001`, and do not substitute
Unraid's usual `PUID`/`PGID` values. Avoid host networking, privileged mode, or
silently dropping hardening flags. If a UI cannot represent a required setting,
use a compatible Compose route rather than claiming equivalent protection.

### Verification limits

Beyond the owner-reported Synology installation above, other Synology models
and GUI versions, Portainer and Unraid are **not yet verified** on physical
installations for this deployment recipe. UI wording and supported
Compose keys vary. Validate the file in the installed manager and verify actual
port bindings, UID/GID, mount modes and health after deployment. Engine-based
automated tests do not establish NAS ACL or GUI compatibility.

## Existing installs: adopt without changing storage

Adoption is optional. Existing Git-based installs can continue using their root
Compose workflow. A published image update does not require adopting this file.

Before switching, record the existing Compose project name, service name,
absolute mount paths, bind address/port, selected image, base URL and proxy
settings. Preserve them exactly. The default project/service remain
`forge-gamesheets`/`app`; use the original project name if it was customized.
Do not create a second project pointing at the same writable data.

Relative `./data` under a downloaded file refers to its new directory, not the
old checkout. Set absolute existing paths before starting. Make the rollback
checkpoint below first. Validate the candidate configuration, stop the old
service, and recreate the same service/project. Do not rebuild or create a new
empty data directory as a migration step.

## Two different updates

### Image only

From the deployment folder, after a stopped-data backup:

```sh
docker compose pull app
docker compose up -d --no-build app
docker compose ps
docker compose logs --tail=30 app
```

Confirm the intended revision in `/health` or Settings and check a game, an
original PDF, and a generated sheet. Pulling an image does not update the saved
Compose definition, paths, GUI stack configuration or optional `.env`.

### Deployment configuration only

Download the desired configuration revision to `compose.yml.new`; never overwrite
a customized active file blindly:

```sh
curl --fail --location \
  https://raw.githubusercontent.com/natsteff/forge-gamesheets/main/deploy/compose.yml \
  --output compose.yml.new
diff -u compose.yml compose.yml.new
docker compose -f compose.yml.new config --quiet
```

Use a commit SHA instead of `main` in the URL when a release requires a specific
configuration. Reapply existing local settings to the candidate, review changes
against the release notes and the resolved configuration, then deliberately
replace the active file. In a GUI, save/export the old stack settings before
editing the stack. Preserve environment values, project identity, mount paths
and proxy/network configuration. A new variable in `.env` does nothing unless
the Compose definition passes it through.

A configuration-only update should not silently select a newer moving image.
Keep the recorded local image available, select its rollback tag or a known
revision, and recreate with `--no-build --pull never`. Verify the running
revision after recreation.

## Rollback checkpoint and recovery

Before any adoption or update:

1. Save a private copy of the current Compose definition, optional `.env` or GUI
   variable settings, project name and actual absolute storage paths.
2. Record the running image ID and revision, and retain that image under a local
   rollback tag before pulling a moving channel.
3. Stop the application and make a permission-preserving backup of its **complete
   data directory**. Maintain the normal independent library backup. Restart the
   old service if the planned update will not immediately follow.

For the standard project and deployment file, this Linux example preserves the
local image and a stopped data snapshot. Set `DATA_DIR` to the real configured
host data path first; the backup directory must be outside it:

```sh
umask 077
DATA_DIR=/absolute/path/to/existing/data
backup_stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="$PWD/backups/$backup_stamp"
mkdir -p "$backup_dir"
cp -p compose.yml "$backup_dir/compose.yml"
if test -f .env; then cp -p .env "$backup_dir/.env"; fi
container_id=$(docker compose ps -q app)
test -n "$container_id" || exit 1
image_id=$(docker inspect --format '{{.Image}}' "$container_id")
rollback_tag="rollback-$backup_stamp"
docker image tag "$image_id" "ghcr.io/natsteff/forge-gamesheets:$rollback_tag"
printf '%s\n' "$rollback_tag" > "$backup_dir/image-tag"
docker compose stop app
sudo tar --numeric-owner -cpf "$backup_dir/data.tar" -C "$DATA_DIR" .
docker compose start app
```

If the backup command fails, do not upgrade; preserve the old container/image
and correct the backup problem. Do not prune the retained rollback image.

**Configuration rollback:** restore the saved definition and its exact previous
environment/GUI settings, leaving the data directory intact if the running image
never changed. Recreate the original project with the retained image and
`--no-build --pull never`.

**Image rollback:** if the new app has started, assume migrations or persistent
changes may have occurred. Stop it and restore the **matching data backup** along
with the previous configuration and image. Preserve the failed/new data directory
under a separate name for investigation instead of overwriting it. Restore
ownership/ACLs and original mount paths, then start the old image. Do not edit
migration records or point older code at a newer database.

With the original configuration restored and the matching data backup in place:

```sh
FORGE_GAMESHEETS_IMAGE_TAG="$(cat "$backup_dir/image-tag")" \
  docker compose up -d --no-build --pull never app
docker compose ps
```

GUI operators should restore the saved stack/container settings and select the
retained image without pulling. Exact filesystem restore commands depend on NAS
ACLs and backup tooling; validate the backup before discarding either data copy.
A moving `main` tag alone is not a rollback checkpoint.

## Automated validation

`python scripts/check_deployment.py` validates the downloaded file in a clean
temporary directory with no checkout files or `.env`, checks defaults and
custom settings, and compares runtime/security settings with root Compose.

`python scripts/check_deployment.py --image LOCAL_IMAGE` additionally uses a
unique disposable Compose project and fixture bind directories to verify:
runtime UID/GID, writable data, read-only library, build identity and health,
persistence through recreation, rejected missing/inaccessible mounts, and
recovery after restoring configuration. It never builds or pulls an image and
never attaches existing data. Fixture directories live in a temporary Docker
volume on the daemon's Linux filesystem and are bound into the app by Compose;
this avoids macOS/Windows host file-sharing ownership translation. The volume is
removed afterward. Root is used only in a short-lived fixture helper to prepare
ownership within that fixture; the application always runs as the image's
non-root user. This does not verify Desktop file-sharing or NAS ACL semantics.

CI runs the bind checks against the exact locally built AMD64 release candidate
before registry publication. Existing AMD64/ARM64 runtime checks and security
scans remain mandatory. Native NAS/GUI acceptance is a separate check.
