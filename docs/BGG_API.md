# Optional BoardGameGeek API setup

Forge GameSheets was approved on 2026-09-14 as a non-commercial, public-facing
application of the BoardGameGeek XML API. This approval does not place a secret
token in Forge. API enrichment is optional and disabled by default.

## Who obtains a token

The administrator of each independently hosted Forge installation registers
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

Restart the Forge container, sign in as an Admin, and use **Settings >
BoardGameGeek > Test BGG connection**. The test makes one request and reports
whether BGG accepted the configured token. Forge never displays the token.

Never put a real token in GitHub, `compose.yml`, `.env.example`, a Docker image,
a screenshot, application data, or a metadata export. Keep the `.env` file with
the installation's other private deployment configuration.

## Behavior without a token

An empty or omitted token is the supported default. Forge does not construct an
API client or make BGG API requests. Library discovery, PDFs, artwork, Sheet
Designer, external title search, and manually saved BGG URLs remain available.

## Request and data boundaries

Forge uses only the documented BGG XML API2 over HTTPS at
`boardgamegeek.com`. Requests are initiated by explicit enrichment actions and
use an `Authorization: Bearer` header. Forge caches selected identifiers and
useful response metadata locally so ordinary use does not depend on BGG being
available. BGG failures never stop local library operation.

Do not use private or undocumented BGG APIs. API-derived data must not be used
to train an AI or language model. A commercial deployment must obtain whatever
commercial permission BGG requires; Forge's software license does not grant
rights to BGG data.

Public-facing API controls include BGG's official, linked **Powered by BGG**
logo at a legible size. The checked-in image is the official small color PNG
provided by BGG and must not be replaced with a recreated mark.

See BGG's current [XML API instructions](https://boardgamegeek.com/using_the_xml_api)
and [XML API Terms of Use](https://boardgamegeek.com/wiki/page/XML%20API%20Terms%20of%20Use).
