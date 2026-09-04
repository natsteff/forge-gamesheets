# Local accounts and QR guest sharing

Status: implemented and published; basic owner validation completed.

## Boundaries

- Upgrades add tables only. Local `python -m app.accounts create-admin` prompts
  for credentials and atomically creates the first Admin and enables protection.
  A persistent activation marker prevents a missing/reset database from silently
  reopening a previously protected data directory. There is no web bootstrap or
  default password. Local recovery resets an Admin without turning protection off.
- Admin: settings, accounts, security policy, sharing controls, and all library
  actions. Contributor: existing content edits/artwork/BGG/rescan and shared
  favorites/pins, plus reading/printing. Reader: library browsing, originals,
  previews, and deliberate reprint generation; no metadata/settings edits.
- QR guest: no account, no library browsing, editing, or generation. A valid
  revocable opaque link permits only its one resource, original PDF and existing
  generated copy. Guest policy defaults to allow; requiring sign-in applies to
  every share request, including old links and direct PDF requests. Revocation
  survives policy toggles. Existing numeric QR URLs are never guest credentials.
- Explicit sharing is Admin-controlled in this first version. Ordinary FORGE
  reprints keep numeric login-required links after activation; a separate shared
  reprint action embeds the secure link. Viewing the original PDF is the genuine
  no-QR alternative. Creating a share does not modify source content.

## Account and session security

Use Argon2id password hashing, passphrases of 15–128 characters, server-side
opaque sessions stored as digests, idle and absolute expiry, HttpOnly host-only
SameSite cookies, and Secure cookies on HTTPS. Preserve same-origin checks on
all mutations, including login/logout. Throttle login attempts before password
verification. Account disabling, role changes, password changes, and recovery
invalidate sessions. Never allow deletion/demotion/disablement of the last
enabled Admin. Admin operations require current-password confirmation.

Authentication requires HTTPS for non-local deployments to protect credentials
in transit; a trusted LAN alone does not encrypt HTTP. Keep the existing
network/container protections. Authentication is not approval for direct public
exposure. Proxy forwarding must be configured correctly.

## Content and compatibility

The library remains shared, not owned by the bootstrap user. Source mounts stay
read-only. Shared guest requests do not expose activity history or record named
user activity. Current shared favorites/pins/history remain shared for signed-in
users. User deletion and per-user collections are deliberately excluded.

Store security events without passwords, session tokens, QR credentials, or
request bodies. Redact share-link credentials in application access logs; the
operator must similarly protect proxy/browser/downloaded-PDF copies of links.
Back up accounts, activation marker, and sharing state with application data.

References: [OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
