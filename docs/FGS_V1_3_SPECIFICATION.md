# FGS 1.3 specification

Status: Implemented and owner-reviewed. Publication is verified separately.

FGS 1.3 extends [FGS 1.2](FGS_V1_2_SPECIFICATION.md), retaining all previous
fields, limits, unique-ID rules and namespaced extensions. Readers accept
versions 1.0–1.3. New blocks require `format_version: "1.3"`; removing them
does not automatically downgrade the file. The structural schema is
[fgs-v1.3.schema.json](schemas/fgs-v1.3.schema.json). Runtime validation also
enforces the semantic constraints below. Unknown ordinary properties are rejected.

## Resource tracker

A `tracker` requires `id`, `type`, nonblank `title` (existing 160-character
limit), `appearance`, and integer `capacity`. Optional properties are
`initial_value` and namespaced `extensions`.

| Appearance | Capacity | Meaning |
| --- | --- | --- |
| `checkboxes` | 1–100 | Independent boxes, not a consecutive progress count |
| `numbered_boxes` | 1–100 | A scalar count with numbered spaces |
| `segmented_bar` | 1–100 | A scalar count with equal-sized segments |
| `current_maximum` | 1–1,000,000 | A scalar current value and fixed maximum |

`initial_value`, when present, is an integer from zero through capacity.
It supplies starting guidance for scalar trackers, not captured play data.
Checkboxes always start unchecked; their optional initial value is printed
guidance only. Omit it when no starting guidance is wanted. Runtime current
values, checked states, timestamps and player health records do not belong in FGS.

```json
{
  "id": "resource-a", "type": "tracker", "title": "Energy",
  "appearance": "current_maximum", "capacity": 10, "initial_value": 7
}
```

This and subsequent examples are block fragments, not complete documents.
Personal measurement logs (blood sugar, weight, etc.) remain a separate future
tables/fields capability. Resource trackers are not persistent health records.

## Reusable paper

A `paper_pattern` requires `id`, `type`, `title`, `pattern`, `sizing`, and
`settings`. Its title may be empty to use the entire area for writing.
Namespaced `extensions` are optional. Patterns are generated vectors, not assets,
backgrounds, arbitrary drawings, or musical notation.

| Pattern | Required settings | Optional settings |
| --- | --- | --- |
| `ruled` | `spacing_pt` 9–36 | `margin_guide_pt` 18–90 |
| `square_grid`, `dot_grid` | `spacing_pt` 7–36 | None |
| `hex_grid` | `side_pt` 7–36 | None |
| `coordinate_grid` | `spacing_pt` 7–36, `origin` (`center`/`bottom_left`), boolean `numbered`, `units_per_step` 0.25–1000, integer `label_every` 1–10, `x_label`, `y_label` | None |
| `tic_tac_toe`, `sudoku` | `board_size_pt` 72–504, `gap_pt` 9–72, `arrangement` (`single`/`repeat`) | None |
| `dots_and_boxes` | Same board settings plus integer `dot_rows`, `dot_columns` 3–21 | None |
| `music_staff` | `staff_style` (`single`/`paired`), `line_spacing_pt` 3–9, `group_gap_pt` 12–72 | `pair_gap_pt` 9–36, required only for paired |
| `tablature` | integer `strings` 4–8, `line_spacing_pt` 4–12, `group_gap_pt` 12–72 | `string_labels` |

Dimensions are points (72 per inch), in increments of 0.25 points. Editors
may display millimeters or inches and round conversions to quarter points.
String labels must contain exactly one string per line, top to bottom; each
label has at most eight Unicode characters and no C0 controls or DEL.
Empty labels are allowed. Paired music consists of two five-line staves;
no clefs, notes, barlines, braces, tuning semantics or MusicXML import are added.

Sizing is exactly one of:

- `{ "mode": "fixed_height", "height_pt": 216 }`: ruled/grids only;
  height 18–720 points, excluding optional section title; also supports coordinate grids and blank boards.
- `{ "mode": "fixed_count", "count": 4 }`: music/tablature only;
  integer 1–40 complete groups. A paired staff counts as one group.
- `{ "mode": "fill_remaining" }`: any pattern; must be the final row's
  only block. Remaining space is computed after margins, preceding content,
  section title and footer reserve. It does not create another page.

Multiple fill blocks, pairing a fill block, or placing content after it are
invalid. Editors refuse such operations and tell the user to choose fixed
sizing first. Fixed patterns can participate in normal one/two-block rows.

Coordinate grids use evenly spaced X/Y axes, positive X rightwards and positive
Y upwards. The center origin provides four quadrants; bottom-left provides
positive coordinates. Axis labels may be empty, have at most 16 Unicode characters,
and exclude C0 controls/DEL. Numerical scale is independent of physical spacing.
`label_every` is the minimum tick interval; the profile may omit additional labels
to prevent collisions without changing the grid or its scale.

Blank boards reuse `paper_pattern` rather than introducing puzzle data. Board size
is the longest side; tic-tac-toe and Sudoku stay square. Dots and Boxes preserves
square playable cells even with unequal row/column counts. Counts refer to dots:
6 × 6 dots gives 5 × 5 boxes. `single` draws one board; `repeat` tiles complete
boards into the assigned area, preserving size and gaps. Insufficient room is an
error, not permission to shrink or crop. Sudoku is an empty 9 × 9 grid with heavy
3 × 3 region boundaries. No clues, puzzle generation, solving or gameplay state
are supported. These remain static content in LiveSheets.

```json
{
  "id": "manuscript", "type": "paper_pattern", "title": "",
  "pattern": "music_staff", "sizing": { "mode": "fill_remaining" },
  "settings": { "staff_style": "single", "line_spacing_pt": 5, "group_gap_pt": 24 }
}
```

## Delivery and LiveSheet behavior

Both editors create/import/export the same blocks and use the same pinned
[Page Rendering Profile 1.3](FGS_PAGE_RENDERING_PROFILE_1_3.md) for preview,
PDF and printing. A paper starter creates one fill section; users do not
manually insert individual staff lines or grid cells. Existing templates remain valid.
Finished print size and copy arrangement are print-job choices, not FGS 1.3
fields. Compact output may uniformly reduce the physical spacing of an entire
composition; use Full Page at actual size when pattern spacing must remain exact.

Forge may enable LiveSheet for a document containing a score table or tracker.
At session creation, the validated template is snapshotted. Shared tracker
values are separate temporary session data: host-only mutation in both scoring
modes, read-only for guests/claimed players. Checkbox changes address independent
indices; scalar values are bounded integers, may start unset, support direct
entry and ±1 controls, and can be reset to their initial value (or unset).
Edits to the source do not change a running session. End/expiry cleanup removes
tracker state with other temporary session data. Paper patterns remain static
writing/reference content; there is no digital ink or MusicXML player.

Studio remains browser-only and has no LiveSheet backend. Saved FGS and ordinary
PDFs never include session values.
