# Game category assignment

Open Games → Assign game categories as an Admin or Contributor. Search by title,
filter by category or Uncategorized, and sort by title or newest added. Select
individual games or all shown games (up to 500 per batch). Add preserves existing
assignments; Remove removes only the chosen categories. Every operation opens a
confirmation page listing the selected games, category choices, and impact.
Confirm and apply performs the change; Cancel makes no changes. The result reports
changed games and keeps filters.

Admins can enable Settings → Library scanning → Import game categories from
folder names. It defaults off, persists in the database, and takes effect on the
next scan without a restart. It applies only to newly discovered games.

- `Yahtzee [Dice]` imports title `Yahtzee`, category Dice.
- `Yahtzee [Dice, Children]` assigns both categories.
- `Yahtzee (Nate’s Favorite) [Dice]` preserves the parenthetical title.

Only one trailing square-bracket list is interpreted. Commas separate categories;
ampersands are literal. Names are trimmed and matched case-insensitively, duplicates
are ignored, and missing categories are created. Invalid/empty lists, reserved
All Games/Uncategorized names, or names over 60 characters leave the title intact.
Folders and PDFs are never renamed or modified. Imported display titles use the
existing override mechanism; later scans do not overwrite manual categories.

For existing entries, enable Preview categories from folder names on the assignment
page and choose Show games. Review the proposed hints, select games, then choose
Apply folder category hints. This is additive, creates missing categories, and
does not change existing game titles. A no-hint game is unchanged.
