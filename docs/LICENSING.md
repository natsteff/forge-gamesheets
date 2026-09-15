# Licensing and version history

Copyright (C) 2026 Nate Steffenhagen

Forge GameSheets is free software licensed under the **GNU Affero General Public
License version 3**, identified by the SPDX expression `AGPL-3.0-only`. The
complete license text is in [`LICENSE`](../LICENSE).

## What the license permits and requires

The AGPL permits personal, nonprofit, educational, and commercial use. It also
permits modification, redistribution, and charging money. It does not permit a
person to distribute a covered version or operate a modified covered version for
network users while withholding the corresponding source and AGPL rights that
the license requires.

Operators who modify Forge and allow users to interact with that modified
version over a network must provide those users a prominent opportunity to
receive its corresponding source. The permanent **Source code** link in Forge's
footer points to the official project. A distributor or operator of a modified
version is responsible for changing that link when necessary so it identifies
the complete corresponding source for the version actually being run.

This summary is explanatory and does not replace the license text.

## User content is separate

Using Forge does not place user content under the AGPL. The Forge software
license does not change the ownership or license of:

- Source PDFs and detected library artwork
- Artwork uploaded by an operator
- FGS documents and exported PDFs created by users
- Library metadata, databases, backups, and configuration
- URLs and other content entered into the application

Users and operators remain responsible for having appropriate rights to that
content.

## Earlier MIT versions

Forge versions through Git commit `91ba590` were publicly offered under the MIT
License included with those versions. Those historical permissions remain with
copies obtained under that license. Subsequent Forge changes are offered under
`AGPL-3.0-only` unless a later release explicitly states otherwise.

## Direct dependencies

Forge depends on third-party packages that retain their own license terms. The
direct runtime dependency review performed for this transition found permissive
MIT, BSD, and Apache-2.0 packages, plus PyMuPDF/MuPDF, whose installed package
metadata identifies its open-source distribution as GNU AGPLv3. Relicensing
Forge under AGPL aligns the application with that PDF dependency; it does not
replace or alter any third-party license.

Review dependency and bundled-asset licensing again before each major release
or material packaging change.
