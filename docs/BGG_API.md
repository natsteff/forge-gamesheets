# Optional BoardGameGeek API setup

FORGE GameSheets was approved on 2026-09-14 as a non-commercial, public-facing
application of the BoardGameGeek XML API. This approval does not place a secret
token in FORGE GameSheets. API enrichment is optional and disabled by default.

## Who obtains a token

The administrator of each independently hosted FORGE GameSheets installation registers
their use at <https://boardgamegeek.com/applications>. After BGG approves it,
the administrator generates a token for that installation. Ordinary users of
the server do not need tokens.

If one person operates test and production servers, separate tokens are
recommended when BGG makes them available. Separate tokens make usage easier to
identify and allow one environment to be revoked without interrupting another.

## Private configuration

Add the approved token to the installation's untracked `.env` file:

```dotenv
FORGE_GAMESHEETS_BGG_API_TOKEN=replace-with-the-private-token
```

Recreate the FORGE GameSheets container so it receives the changed environment, sign in as
an Admin, and use **Settings > BoardGameGeek integration > Test BGG connection**.
The test makes one request and reports whether BGG accepted the configured token.
FORGE GameSheets never displays the token.

Never put a real token in GitHub, `compose.yml`, `.env.example`, a Docker image,
a screenshot, application data, or a metadata export. Keep the `.env` file with
the installation's other private deployment configuration.

## Behavior without a token

An empty or omitted token is the supported default. FORGE GameSheets does not construct an
API client or make BGG API requests. Library discovery, PDFs, artwork, Sheet
Designer, external title search, and manually saved BGG URLs remain available.

## Request and data boundaries

FORGE GameSheets uses only the documented BGG XML API2 over HTTPS at
`boardgamegeek.com`. Requests are initiated by explicit enrichment actions and
use an `Authorization: Bearer` header. FORGE GameSheets caches selected identifiers and
useful response metadata locally so ordinary use does not depend on BGG being
available. BGG failures never stop local library operation.

## Matching workflow

Admins and Contributors open **Edit game entry → BoardGameGeek integration** and
choose **Find BoardGameGeek match**. FORGE GameSheets searches for the entered title and
automatically saves a result only when one returned title is an exact match
after conservative normalization and any year tie-break. Unresolved duplicate
titles, partial matches, and other ambiguous results remain unlinked until the
user selects a candidate.
For a newly discovered folder ending in a standalone `(YYYY)`, the title is
searched without that suffix and the year breaks ties between otherwise exact
matches; it never forces a mismatched or uncertain result. Automatically
matched new games share detail requests in groups of up to 20, while each
new game still needs its own search. Pending details survive a restart
and a failed detail batch can be retried without repeating successful searches.
When a game is already linked, every different-match search requires an explicit
selection so an existing association is never replaced silently.

The manual URL fallback is the authoritative override when title search cannot
find the intended entry. With a token configured, FORGE GameSheets looks up the exact ID in
the supplied URL without running another title search. It replaces the current
association only after that ID is verified; a missing entry or temporary API
failure leaves the existing association unchanged.

A linked entry offers Game and Files shortcuts, metadata refresh, a different
match search, and association removal. Refresh looks up the already selected BGG
ID and cannot silently switch the association. These explicit actions do not run
during a library scan. The browser returns to the integration section after an
action so results and errors remain visible.
Successful metadata lookups also attempt a separate unauthenticated inspection
of the main game's canonical redirect to capture its URL slug. This bounded
request never forwards the API token, follows redirects or reads HTML. If it
fails, API metadata can still be saved; missing-slug Files/Versions links fall
back to the main game page. Refresh repairs older associations when resolution
succeeds. An explicit **Resolve BGG page link** action is also available without
an API token. No page view or library scan makes these requests.

Do not use private or undocumented BGG APIs. API-derived data must not be used
to train an AI or language model. A commercial deployment must obtain whatever
commercial permission BGG requires; FORGE GameSheets’ software license does not grant
rights to BGG data.

Public-facing API controls include BGG's official, linked **Powered by BGG**
logo at a legible size. The checked-in image is the official small color PNG
provided by BGG and must not be replaced with a recreated mark.

See BGG's current [XML API instructions](https://boardgamegeek.com/using_the_xml_api)
and [XML API Terms of Use](https://boardgamegeek.com/wiki/page/XML%20API%20Terms%20of%20Use).
