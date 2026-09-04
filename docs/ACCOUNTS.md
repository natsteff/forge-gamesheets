# Accounts and QR sharing

Local implementation pending owner review. Accounts are optional: upgrading
does not activate login. Without local setup, everyone who can reach Forge
continues to have trusted-operator access. Do not expose that mode to untrusted users.

## Activate deliberately

Use a terminal **on the host running the intended Forge installation**, in its
Compose directory. Start the updated build first. On the development Mac:

```sh
cd /Users/nate/Documents/Codex/Forge-GameSheets
./scripts/build && docker compose up -d
```

When ready to require sign-in on that installation, run this **separately**:

```sh
docker compose exec app python -m app.accounts create-admin
```

Enter a username and a new 15–128-character passphrase at the prompts. No default
password or public setup URL exists. Passwords are not command-line arguments.
Successful setup immediately protects the existing shared library; it does not
move PDFs, change library permissions, or assign existing content to one owner.
Sign in, then use **Settings → Accounts and QR access** to add accounts.

Non-local sign-in requires HTTPS through a correctly configured trusted proxy.
Localhost HTTP is supported for development. Establish HTTPS before activating
on a LAN server. Keep the direct backend port protected; accounts alone do not
make public exposure appropriate. External proxy authentication can still block
guest QR access independently of Forge's setting.

## Permissions

| Access | Allowed |
| --- | --- |
| Admin | All library actions, settings, accounts, QR policy and explicit sharing |
| Contributor | Browse/print, edit existing metadata/artwork/BGG associations, rescan, shared favorites/pins |
| Reader | Browse, view/download PDFs and previews, generate/regenerate ordinary reprints |
| QR guest | Only the specifically shared original and already-generated shared reprint; no library browsing or generation |

Favorites, pins, recent items, and history remain shared, not personal collections.
PDF uploads, new-game uploads, public registration, email recovery, MFA, and SSO
are not included. Account disabling, role updates, and password changes invalidate
that account's sessions. The last enabled Admin cannot be disabled or demoted.
Sensitive account/sharing controls require the acting user's current passphrase.

## QR behavior

Existing numeric `/r/123` QR links require sign-in after activation. They are not
secret credentials. An Admin can instead create a **shared FORGE Reprint** on
the resource's reprint page, explicitly acknowledging access by anyone with
the secure link. The default policy allows that link without login; unchecking
guest access requires Reader-or-higher sign-in on every shared page/PDF request,
including previously printed links. Revoking a resource link makes it unusable;
creating another gives a new link. Toggling guest policy never restores revoked links.

Shares grant access to the current resource at that entry, not a frozen snapshot.
Changing its source file can change what guests receive. Review or revoke shares
before replacing content. Guests cannot enumerate other resources or trigger rendering.

There is one derived reprint slot per resource. Ordinary regeneration can replace
a shared copy with a login-required numeric-link copy; the shared original remains
available. An Admin can generate the shared copy again. Source/base-URL changes can
also require regeneration. If rendering fails after explicit sharing approval,
the share can remain active for the original; revoke it if access is no longer wanted.

The original PDF is the no-FORGE-QR option. Notices stay on the web page, not the
printed footer. Treat shared PDFs/URLs as access credentials: anyone receiving
them can pass them on. Downloaded copies cannot be recalled, and links do not
make a private server reachable from outside its network.

## Recovery and data

From the same local Compose directory, the operator can recover an Admin:

```sh
docker compose exec app python -m app.accounts recover-admin
```

This creates or restores the named Admin and invalidates all sessions without
turning protection off. It does not reset library content or revoke existing QR
shares. There is no web reset or disable-authentication switch.

Back up the complete application data directory, including SQLite and the hidden
`.authentication-required` marker, alongside the source library. A retained marker
with missing/reset account state fails closed and requires local recovery.
Replacing the entire data directory loses this protection and represents a new
installation: do not restore only selected files or downgrade to a pre-account
release on a protected deployment. A missing share secret/database also invalidates
old secure QR links. Follow the existing backup guidance rather than deleting data
to solve login problems.

## Security limits and review

Navigation groups Games, Quick access, and Account into desktop dropdowns, with
History separate. The mobile Menu shows the same groups with directly visible
links. Admins with accounts enabled can open Users from Account; the Settings
shortcut remains available. Readers and Contributors do not see Users or Settings.

Passphrases use Argon2id; sessions are random opaque cookies with server-side
digests, a 30-minute idle timeout and 12-hour absolute lifetime. HTTPS cookies
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
Authentication-related responses disable browser caching, but downloaded copies
are outside server control. Perform the planned ASVS-focused and independent
security reviews before a major release; this feature is not an ASVS certification.
