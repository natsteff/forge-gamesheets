# Local accounts and resource-scoped QR access

Status: implemented and published; basic owner validation completed.

## Boundaries

- Upgrades add tables only. Local `python -m app.accounts create-admin` prompts
  for credentials and atomically creates the first Admin and enables protection.
  A persistent activation marker prevents a missing/reset database from silently
  reopening a previously protected data directory. There is no web bootstrap or
  default password. Local recovery resets an Admin without turning protection off.
- Admin: settings, accounts, per-resource QR policy, and all library
  actions. Contributor: existing content edits/artwork/BGG/rescan and shared
  favorites/pins, plus reading/printing. Reader: library browsing, originals,
  previews, and deliberate reprint generation; no metadata/settings edits.
- QR guest: no account, no library browsing, editing, or generation. The stable
  numeric QR address permits only its one resource, original PDF, and existing
  generated copy. Access is public by default. An Admin can require sign-in for
  one resource, and that policy is checked on every landing-page and PDF request.
- Every FORGE Reprint embeds the same stable resource address. Changing access
  policy never modifies source content and does not require a new QR code.

## Account and session security

Use Argon2id password hashing, passphrases of 15–128 characters, server-side
opaque sessions stored as digests, idle and absolute expiry, HttpOnly host-only
SameSite cookies, and Secure cookies on HTTPS. Preserve same-origin checks on
all mutations, including login/logout. Throttle login attempts before password
verification. Account disabling, role changes, password changes, and recovery
invalidate sessions. Never allow deletion/demotion/disablement of the last
enabled Admin. Admin operations require current-password confirmation.

Session expiry is an Admin-controlled library policy. Standard sessions default
to 12 hours of inactivity and a 7-day maximum. Login may offer a per-device
remembered choice, defaulting to a 30-day maximum with no inactivity limit.
Admins may disable that choice or explicitly set a limit to Never; browsers may
still discard persistent cookies independently. Policy reductions are enforced
against existing server-side sessions on their next request.

Authentication requires HTTPS for non-local deployments to protect credentials
in transit; a trusted LAN alone does not encrypt HTTP. Keep the existing
network/container protections. Authentication is not approval for direct public
exposure. Proxy forwarding must be configured correctly.

## Content and compatibility

The library remains shared, not owned by the bootstrap user. Source mounts stay
read-only. QR guest requests do not expose activity history or record named
user activity. Current shared favorites/pins/history remain shared for signed-in
users. User deletion and per-user collections are deliberately excluded.

Store security events without passwords, session tokens, or request bodies.
Back up accounts, the activation marker, and per-resource access state with
application data.

References: [OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
