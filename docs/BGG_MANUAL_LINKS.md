# BGG without an API token

Full game URLs preserve the BGG slug (for example, `53412/crag`). The edit field
shows the saved canonical URL. ID-only and older associations can still open both
the Game and Files pages because those destinations are derived from the BGG ID.
Slugs are not inferred from local display titles; they are retained across
updates to the same ID and cleared when the ID changes.

Admins and Contributors can open **Edit game entry → BoardGameGeek integration**,
expand the manual fallback, and paste a full BoardGameGeek URL with both numeric
ID and game-name slug into **Full BGG game URL**.
Bare IDs and URLs without a slug are rejected without changing saved data.
Forge extracts and
stores the ID locally; it does not verify the entry or fetch data. Manual saves
replace any prior BGG cached metadata and disable automatic matching for the game.
Forge labels these records as unverified and shows the local library title
separately so it is not mistaken for a BGG-provided title.
Local game titles, categories, artwork, and PDFs remain unchanged.

Unlinked game pages offer **Open BGG website search** using the displayed local
title. Linked pages offer View on BGG and BGG Files. External links open a new tab
with no opener or referrer. Readers can follow links; only editors can change them.
Removing the association restores the search shortcut. All external destinations
are constructed on the fixed BGG domain, never directly from submitted URLs.

To use artwork, visit BGG and obtain an image you have permission to reuse, then
use the existing local artwork upload. No automatic scraping, downloads, or image
hotlinking are part of this workflow. BGG API enrichment remains optional and
requires its own token/configuration. Manual associations use the same BGG ID
storage so later integration does not require a competing identifier.
