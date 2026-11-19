# Local accounts and resource-scoped QR access

Status: implemented and published; basic owner validation completed.

## Boundaries

- Fresh full-application installations default to blocking library access until
  browser owner setup succeeds. An explicit deployment access mode chooses
  `owner` or account-free `trusted` access. Enabled accounts always override
  `trusted`; the setting cannot disable authentication or bypass recovery.
  Omitted settings preserve existing pre-model open installations; explicitly
  choosing `owner` requires their activation. Protected installations remain
  protected.
  No default credentials or console setup code is required. The first visitor
  to complete setup claims the installation, an explicit trusted-deployment
  tradeoff; operators must complete setup before sharing access.
- Migration 38 distinguishes new data from pre-existing migration history.
  A private first-owner installation marker preserves that distinction across
  interrupted initialization. Setup state is persisted, not inferred from
  an empty users table. The authentication marker still makes incomplete
  protected state fail closed. Local recovery remains available.
- Browser setup uses HTTPS (localhost HTTP allowed), same-origin mutation
  checks, expiring signed cookie/form tokens, persistent throttling, existing
  password screening/hashing, and a serialized activation transaction.
  Existing CLI bootstrap/recovery commands remain supported.
- Admin: settings, accounts, per-resource QR policy, and all library
  actions. Contributor: existing content edits/artwork/BGG/rescan and shared
  favorites/pins, plus reading/printing. Reader: library browsing, originals,
  previews, and deliberate reprint generation; no metadata/settings edits.
- QR guest: no account, no library browsing, editing, or generation. The stable
  numeric QR address permits only its one resource, original PDF, and existing
  generated copy. Access is public by default. An Admin can require sign-in for
  one resource, and that policy is checked on every landing-page and PDF request.
- Every FORGE GameSheets Reprint embeds the same stable resource address. Changing access
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
