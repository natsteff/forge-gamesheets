# Global Links directory

Forge's global directory is a server-rendered application feature, not an FGS
format extension. Existing per-game primary/alternate links are unchanged, and
FGS Studio and standalone Designer mode do not initialize these records.

## Browsing and favorites

Navigation → Links opens a single page. Personal Favorites appear first only
when the signed-in account has selections; Forge Favorites follow, then All
Links grouped by category. Forge Favorites are initially empty. All Links keeps
favorite entries in their categories. The same link can appear in both favorite
sections without creating duplicate records.

All Links uses compact rows matching the Score Sheets listing, alphabetically
by name within each category (case-insensitive, ties use record ID).
The star toggles a signed-in user's personal favorite. The pin (⌖) adds/removes
a shared Forge Favorite and is Admin-only, as are Edit and confirmed Delete.
Open is available to everyone who can view the directory and opens the external
site in a new tab. Admins have Add link, Manage categories and Add missing starter
links at the top. Disabled entries are grouped and alphabetical in a collapsed
Admin-only section; pinning one does not enable it. The old management URL redirects
to Links, as does the Settings shortcut. Category editing is a separate Admin tool.

All signed-in roles can add/remove only their own personal favorites. The
user identity comes from the session, never a submitted account ID. Without
accounts, only the shared Forge Favorites are available. With accounts enabled,
anonymous or resource-scoped QR visitors cannot access the directory. Readers
and Contributors cannot manage links or categories; Admins can. Without accounts,
the existing trusted-operator access model applies.

## Admin management

Links provides add/edit/delete, enabled status, provenance, category assignment
and Forge Favorite selection. Category order and Forge Favorites order remain
configurable (lower numbers first). Per-link directory order is no longer an
editor field or sorting input; legacy values remain stored for compatibility.
Names, descriptions and categories are escaped plain text, not HTML. Disabling
retains records and favorite selections but hides them everywhere outside
the Admin-only disabled section. Deleting a link requires explicit confirmation and removes its
personal favorites. Delete opens a focused confirmation page with Delete link
and Cancel; visiting that page or cancelling does not change records.
Re-enabling restores retained favorites; recreating a
deleted starter creates a new link identity without old personal selections.

Categories can be created, renamed and reordered. A nonempty category must have
its links moved to another category before deletion; management offers that move
as part of the confirmed deletion transaction. There is no silent deletion of
category contents. New categories suggest one higher than the highest category
order (1 when empty, capped at the supported maximum of 9999); Admins can change
the suggested value. Up to 100 categories and 500 links are supported. Names are
limited to 120 characters, descriptions to 400, category names to 80, URLs to
2000, and order numbers to 0–9999.

## Starter file and upgrades

`app/defaults/links.json` is the version-controlled starter source, with file
schema version 1. It contains categories (`key`, `name`, `position`) and links
(`key`, `name`, `url`, `description`, `category_key`, `source_type`, `enabled`,
`position`, `forge_favorite`, `favorite_position`). Initial favorites are all
false. Source type is `official`, `third_party` or `community` and represents
provenance only.

Migration 29 creates the tables and seeds the current bundled file atomically.
It runs once for both new installs and upgrades. Subsequent startup/migrations
do not resynchronize the file. Admin edits, disabling, moves and deletions survive
upgrades. Existing stable keys must never be renamed or reused for another
destination; changing a label or URL in the file affects new installations only.

The confirmed Add missing starter links action inserts only missing stable link
keys and recreates missing starter categories. It never overwrites an existing
starter, even if renamed, moved or disabled. If a custom category already has a
starter category's name, it is reused without changing its settings. Custom links
are independent records; matching URLs do not collapse them into starters. A
starter key is provenance, not an edit/delete restriction. Database IDs and
timestamps are generated locally and do not belong in the file.

Back up and restore the main Forge database using the normal application-data
backup procedure; it stores categories, links, starter identities, timestamps,
shared favorites and personal favorites. The metadata-portability export is not
a replacement for a complete database backup and does not export this directory.

## External content boundary

Only absolute HTTP/HTTPS URLs without embedded credentials are accepted. Reject
executable/local schemes, malformed ports, whitespace, controls and backslashes.
Links navigate directly, clearly marked external, in a new tab with
`noopener noreferrer`. No destination fetch, preview, health check, scraping,
proxying, download, mirroring or bundling of third-party resources occurs.
Descriptions and provenance do not assert licensing or safety. Downloadable
content remains subject to the destination's access and copyright terms.

The starter destinations are supplied by the owner. During implementation, most
pages were accessible through a read-only web check; GameScore's scoresheets
page, the Apple App Store entry and BoardGameGeek could not be confirmed by that
check. They remain editable supplied links, not guaranteed available resources.
