# Accounts and QR access

Accounts are optional: upgrading does not activate login. Without local setup,
everyone who can reach Forge continues to have trusted-operator access. Do not
expose that mode to untrusted users.

## Activate deliberately

Use a terminal **on the host running the intended Forge installation**, in its
Compose directory. Start the current container first:

```sh
cd /opt/forge-gamesheets
docker compose up -d
```

For access from another device, configure the HTTPS reverse proxy and verify that
the Forge sign-in page loads over its final HTTPS hostname first. Follow the
[Nginx Proxy Manager example](deployment.md#https-with-nginx-proxy-manager). A
self-signed/private-CA certificate works when the client trusts that CA. Do not
activate accounts while relying on direct LAN HTTP access.

Confirm the current Compose file passes the proxy settings into the container:

```sh
docker compose exec app env | grep -E 'FORWARDED|BASE_URL|ALLOWED_HOSTS'
```

When HTTPS is working—or when using localhost only—run this **separately**:

```sh
docker compose exec app python -m app.accounts create-admin
```

Enter a username and a new 15–128-character passphrase at the prompts. No default
password or public setup URL exists. Passwords are not command-line arguments.
Successful setup immediately protects the existing shared library; it does not
move PDFs, change library permissions, or assign existing content to one owner.
Sign in, then use **Admin → User Accounts** to add accounts. QR codes remain
resource-only and public by default. An Admin may require sign-in for an
individual resource from its FORGE Reprint page.

Non-local sign-in requires HTTPS through a correctly configured trusted proxy.
Localhost HTTP is supported for development. Establish HTTPS before activating
on a LAN server. Keep the direct backend port protected; accounts alone do not
make public exposure appropriate. External proxy authentication can still block
public QR access independently of Forge's resource setting.

## Permissions

| Access | Allowed |
| --- | --- |
| Admin | All library actions, settings, accounts, and per-resource QR policy |
| Contributor | Browse/print, edit existing metadata/artwork/BGG associations, rescan, shared favorites/pins |
| Reader | Browse, view/download PDFs and previews, generate/regenerate ordinary reprints |
| QR guest | Only the QR code's original and already-generated reprint; no library browsing or generation |

Favorites, pins, recent items, and history remain shared, not personal collections.
PDF uploads, new-game uploads, public registration, email recovery, MFA, and SSO
are not included. Account disabling, role updates, and password changes invalidate
that account's sessions. The last enabled Admin cannot be disabled or demoted.
Sensitive account controls require the acting user's current passphrase.

## QR behavior

Every FORGE Reprint uses its stable numeric `/r/123` address. That address is
public by default, but exposes only its one resource, original PDF, and existing
generated copy. Guests cannot enumerate the library or trigger rendering. An
Admin can require Reader-or-higher sign-in for an individual resource. The
policy is checked on every landing-page and PDF request, so the same printed QR
code responds immediately when the setting changes.

The QR address resolves to the current resource at that entry, not a frozen
snapshot. Changing its source file can change what guests receive. Review its
access setting before replacing content. Source or base-URL changes can require
reprint regeneration; changing only the access setting does not.

The migration from the earlier test-only secure-link design retires `/s/…`
addresses and removes their tokens. After upgrading that test installation, run
**Admin → FORGE Reprints → Create or refresh all reprints** once so every printed
copy uses its stable `/r/{resource-id}` address.

The original PDF is the no-FORGE-QR option. Notices stay on the web page, not the
printed footer. Treat public QR PDFs/URLs as shareable links: anyone receiving
them can pass them on. Downloaded copies cannot be recalled, and links do not
make a private server reachable from outside its network.

## Recovery and data

From the same local Compose directory, the operator can recover an Admin:

```sh
docker compose exec app python -m app.accounts recover-admin
```

This creates or restores the named Admin and invalidates all sessions without
turning protection off. It does not reset library content or QR restrictions.
There is no web reset or disable-authentication switch.

Back up the complete application data directory, including SQLite and the hidden
`.authentication-required` marker, alongside the source library. A retained marker
with missing/reset account state fails closed and requires local recovery.
Replacing the entire data directory loses this protection and represents a new
installation: do not restore only selected files or downgrade to a pre-account
release on a protected deployment. A missing database also loses per-resource QR
restrictions. Follow the existing backup guidance rather than deleting data to
solve login problems.

## Security limits and review

Navigation groups Games, Quick access, Admin, and Account into desktop dropdowns,
with Sheet Designer and History as separate top-level links. Sheet Designer is
available to Admins and Contributors. The mobile Menu shows
the same permitted groups with directly visible links. Admins can open FORGE
Reprints, Metadata portability, Settings, and User Accounts from Admin and can
open the Sheet Designer.
Account contains personal account actions. Readers and Contributors do not see
the Admin menu; Readers also do not see Sheet Designer.

Sheet Designer drafts are system-wide shared content, comparable to the shared
PDF library rather than private account documents. Admins and Contributors can
open, change, export, duplicate, and delete every saved draft. Export important
`.fgs` source periodically and before significant shared changes or deletion.

Passphrases use Argon2id; sessions are random opaque cookies with server-side
digests. By default, standard sessions have a 12-hour inactivity limit and a
7-day maximum; a person may opt into a 30-day remembered session on a trusted
device, with no inactivity limit. Admins can change these limits under Settings,
disable the remembered option, or explicitly select Never. Shorter policies
apply to existing sessions on their next request. A browser or operating system
may still discard a cookie before a server-side Never limit. HTTPS cookies
are Secure; all session cookies are HttpOnly and SameSite Strict. Public login
attempts have 15-minute limits (10 per username, 30 per client address, 100
installation-wide). Signed-in password confirmations have a separate budget of
10 attempts per authenticated account per 15 minutes, isolated from public login
traffic and other accounts. Both budgets count successful attempts. A busy
administrator may need to wait; this is throttling, not an Internet-scale abuse
defense. Trusted proxy configuration affects client address attribution.

New and changed passwords are screened offline against Django's bundled 19,640-entry
common-password list, repeated common passwords, and single-character repetition.
Passwords never leave this installation for screening. Existing passwords continue
to work. This is not a comprehensive breached-password check or ASVS certification.
Application access logs omit query strings, including encoded QR redirect targets;
operators must apply equivalent protection to reverse-proxy logs.

Account/sharing events retain at most 1,000 entries and show the latest 30 to
Admins, displaying readable actions, current actor usernames, and target account
names or game/resource titles alongside IDs. Missing targets retain their IDs;
local setup/recovery is labeled Local operator. Names reflect current records,
not historical snapshots. This is not comprehensive content auditing. App access logs redact
sharing tokens; operators must also redact proxy logs and protect backups.
These security events remain separate from the general Activity History page,
which points administrators to User Accounts for authentication and account
changes.
Authentication-related responses disable browser caching, but downloaded copies
are outside server control. Perform the planned ASVS-focused, maintainer-led
security review before a major release; this feature is not ASVS certification.
