# FGS trackers and reusable paper — specification draft

Status: **Historical design proposal, superseded by the local FGS 1.3 implementation.**

The owner approved implementation of printable content and basic shared LiveSheet
trackers. Use [FGS 1.3](FGS_V1_3_SPECIFICATION.md) and its rendering profile as
the current contract; this proposal records earlier reasoning, not additional
implemented capabilities. FGS 1.2 remains the published release until approval.

Companion: [editor and delivery design](FGS_TRACKERS_AND_PAPER_DESIGN.md).

## 1. Scope and compatibility

Add two block types to the existing full-width / paired equal-width row model:

- `tracker`: bounded resource or completion tracking.
- `paper_pattern`: generated writing patterns, including blank music manuscript.

Preserve existing headers, logos, footers, notes, score tables, Designer Notes,
accent behavior, strict validation, portable IDs and extension preservation.
No coordinates, HTML, scripts, remote assets, custom fonts or separate music
file dependency. No changes to published 1.0–1.2 field meanings or appearance.
Existing readers reject the new version rather than silently losing blocks.
Editors promote a document only when a new capability is used, and never
downgrade it merely because a logo/footer is changed or a new block is removed.

The format extension, rendering profile extension and application interaction
are separate contracts. Ship the new blocks in both editors together, using
the canonical renderer in Forge's `packages/fgs-renderer` and its pinned Studio
distribution. A separate renderer repository is not required.

## 2. Tracker block

Common fields: existing `id`, `type`, `title`, optional `extensions`.
Proposed additional fields:

| Field | Meaning / proposed limit |
| --- | --- |
| `appearance` | `checkboxes`, `numbered_boxes`, `segmented_bar`, `current_maximum` |
| `capacity` | Required positive integer; 1–100 for box/bar styles, 1–1,000,000 for current/maximum |
| `initial_value` | Optional integer, 0 through capacity; absent means no prescribed starting value |

Title uses the existing block title length and plain-text validation rules.
All tracker values in this first design are integers. Decimal measurements,
units, date/time and longitudinal records belong to a future general table /
field proposal, not to this block. Labels such as Health, Mana, Ammunition,
Rounds or Practice sessions are ordinary author text, not special game rules.

### Meaning and state

- **Checkboxes:** independent completed/selected items. Runtime state is a
  bounded Boolean array of exactly `capacity` entries. If `initial_value` is
  supplied, that many leading boxes start selected. Unselecting an earlier box
  does not clear later boxes.
- **Numbered boxes:** one bounded resource value. Boxes are labeled 1 through
  capacity; boxes up to the value are selected. This is not independent state.
- **Segmented bar:** the same bounded resource value represented by filled
  leading segments, with a visible numeric current/maximum readout when filled.
- **Current/maximum:** one value displayed beside the capacity; direct entry
  and increment/decrement are interaction choices, not executable FGS content.

The template stores only a prescribed initial value, never a participant's
current value. Runtime state is keyed by block ID in a separate session record.
No formulas, cross-tracker dependencies, hidden scoring by title, negative
values, temporary-health rules or automatic medical interpretation.

Template preview and ordinary template PDF render all marking spaces empty.
Current/maximum shows a writable blank followed by `/ capacity`. A supplied
initial value appears as small literal guidance, `Start: N`, consistently in
preview and PDF; it does not look like a saved result. A future explicitly
labeled filled-record export may show runtime values, but is not part of this
increment. Editors show a warning before changing checkbox versus scalar
appearance: live sessions continue using their immutable original snapshot.

Initial tracker JSON (illustrative fragment):

```json
{
  "id": "health",
  "type": "tracker",
  "title": "Health",
  "appearance": "current_maximum",
  "capacity": 35,
  "initial_value": 35
}
```

### Personal health records are a different capability

Daily blood sugar, weight and blood-pressure records require dated measurement
rows, units and optional context. Do not present a resource tracker as a
substitute for those logs. Existing score tables can approximate printed logs,
but a general-purpose table/field design is future work, not silently included
here. No built-in medical ranges, diagnostic colors or treatment advice.
Persistent personal records require a separate privacy/lifecycle decision;
temporary LiveSheets must not be advertised as a durable health journal.

## 3. Paper-pattern block

Common fields: existing `id`, `type`, `title`, optional `extensions`. Empty title
is valid and consumes no title space. A pattern is one generated section: users
do not add individual grid rows or individual staves.

Proposed fields:

| Field | Meaning |
| --- | --- |
| `pattern` | `ruled`, `square_grid`, `dot_grid`, `hex_grid`, `music_staff`, `tablature` |
| `sizing` | Exactly one of the sizing definitions below |
| `settings` | A strict pattern-specific object; irrelevant properties rejected |

Use PDF points for canonical numeric geometry, matching the existing renderer.
Authoring UI can show mm/inches; convert and store once to the nearest 0.25 pt.
Dimensions must be finite and at 0.25 pt increments. Rendering must not repeatedly
convert between units. No physical-unit scaling to make an overflowing sheet fit.

### Sizing

- `{"mode":"fill_remaining"}`: allowed only in the final row, with exactly
  one full-width block. At most one per document. Following rows, paired blocks,
  or multiple fill blocks are invalid. Consume available space after ordinary
  content and the pattern's own title, above the existing reserved footer area.
- `{"mode":"fixed_height","height_pt":216}`: allowed for ruled / grid patterns;
  proposed height 18–720 pt. A valid height can still overflow the chosen page.
- `{"mode":"fixed_count","count":8}`: allowed for music/tab groups; 1–40 groups.

Music staff means a complete group of five lines, not a single horizontal line.
Paired piano staff means one group containing two five-line staves. Tablature
means one group containing the chosen number of string lines. Count always
refers to these complete groups.

### Pattern settings

| Pattern | Proposed settings and defaults |
| --- | --- |
| Ruled | `spacing_pt`: 18 (range 9–36); optional `margin_guide_pt`: absent (range 18–90) |
| Square / dot | `spacing_pt`: 14.25 (range 7–36) |
| Hex | `side_pt`: 14.25 (range 7–36); fixed flat-top orientation initially |
| Music staff | `staff_style`: `single` or `paired`; `line_spacing_pt`: 5 (range 3–9); `group_gap_pt`: 24 (range 12–72); paired `pair_gap_pt`: 18 (range 9–36) |
| Tablature | `strings`: 6 (range 4–8); `line_spacing_pt`: 7 (range 4–12); `group_gap_pt`: 24 (range 12–72); optional `string_labels`: exactly one plain-text label per string, maximum 8 characters each |

`pair_gap_pt` measures from the bottom line of the first staff to the top line
of the second; `group_gap_pt` measures from the bottom line of a complete group
to the top line of the next group. Single-staff settings cannot contain a paired
gap. A ruled margin guide must leave at least 36 pt of writing width or fail fit.
Tab labels read top-to-bottom, with no automatic instrument/tuning assumptions.
Music is blank manuscript: no clefs, notes, time signatures, engraving, MusicXML
import or automatic note placement in this increment.

Example (illustrative fragment):

```json
{
  "id": "manuscript",
  "type": "paper_pattern",
  "title": "",
  "pattern": "music_staff",
  "sizing": {"mode": "fill_remaining"},
  "settings": {
    "staff_style": "single",
    "line_spacing_pt": 5,
    "group_gap_pt": 24
  }
}
```

## 4. Proposed rendering-profile extension

Keep current page sizes, 36 pt margins, row gaps, paired gaps, bundled fonts,
title accent/contrast rules and footer reservation. Reuse the point-based
display list for SVG and vector PDF; never approximate patterns with CSS
backgrounds or raster page images. A new profile revision and conformance
fixtures are required before claiming support; do not edit historical profiles.

### Pattern geometry

- Origin is the pattern body top-left after any measured title. Body title uses
  the existing section-title geometry. All marks stay inside the body rectangle.
- For ruled paper, lines start one spacing below the body top, then repeat at
  exact spacing through the last fitting line. The optional guide is vertical
  at the specified offset from the body's left edge.
- Square grids include the top and left origin lines; repeat by spacing without
  drawing a partial interval at the bottom/right edge. Dots use the same origin
  and lattice spacing; dots whose radius would cross a body edge are omitted.
- Hex grids use regular flat-top hexagons with the specified side length. Centers
  follow a standard staggered lattice: horizontal step 1.5 times side, vertical
  step sqrt(3) times side, alternating columns offset by half a vertical step.
  Anchor the first center at `(side, sqrt(3)*side/2)` relative to body origin.
  Draw only complete hexagons inside the body, deduplicating shared edges.
- Single music group height is four times line spacing; paired height is eight
  times line spacing plus pair gap. Tab group height is `(strings - 1)` times
  line spacing. Fixed-count height is count times group height plus count-minus-
  one times group gap. Labels share the pinned body font and reserve a measured
  left gutter; all tab lines start at the same measured gutter boundary.
- Fill music/tab repeats the largest whole number of groups that fits. Require
  at least one; otherwise report overflow. Never truncate a group or squeeze
  spacing. Unused space remains below the final group. Optional title does not
  count as a group. Require one full interval for ruled/grid fill sections.
- Template paper marks use neutral `#808080`, 0.5 pt strokes; dots have 0.75 pt
  radius. These are writing guides, not UI text; pattern color is independent
  of accent. Defer extra line-color/stroke controls until print examples are
  reviewed. Viewing zoom does not change the PDF's physical dimensions.

### Tracker geometry

Checkbox and numbered cells are 18 pt squares with 4 pt gaps. Wrap left-to-right
into the maximum complete cells fitting the block width; row gaps are 4 pt.
The profile's existing title/body spacing applies. Numbered labels use the
bundled body font at 8 pt. Capacity 100 therefore remains bounded but can
overflow a page; report it rather than shrink cells.

Bars are 18 pt high, with equal segments and 0.5 pt internal rules. Each segment
must be at least 6 pt wide; otherwise fail fit and suggest current/maximum or
numbered boxes. Current/maximum uses the bundled body font at 12 pt and a
minimum 54 pt writable underline. Marks use neutral rules; label uses existing
section title accent. Initial-value guidance uses existing body text styling.
Template rendering never uses selected color to imply entered user data.

### Fit and determinism

Fixed-size content keeps existing overflow behavior. Fill remaining is a bounded
allocation, not automatic pagination. Calculate all prior rows and reserved
footer geometry first, then the final fill body. If earlier content already
overflows, the whole page fails fit. Show the offending section and reason in
both editors; prevent PDF export rather than clipping or rasterizing.

SVG/PDF consume identical coordinates, text and fit results. Establish numeric
tolerances for floating-point hex coordinates in fixtures; do not demand
identical antialiased pixels between viewers. Print instructions should explain
that physical spacing assumes actual-size / 100% printing, not printer scaling.

## 5. LiveSheet boundary (proposal requiring owner review)

Printable blocks do not by themselves authorize new session/persistence rules.
Recommended interactive milestone: sheet-level trackers controlled by the host
and designated single scorer, using existing authorization, immutable snapshot
and session lifetime. Participants see values read-only unless explicitly
authorized. Per-player trackers/character ownership are deferred pending design.

If approved: tracker-only sheets become eligible; paper-only sheets do not become
interactive merely because they contain a pattern. Pattern blocks stay static
presentation and provide no drawing canvas or retained handwritten data.
Reload preserves session state; reset is explicit, authorized and confirmed.
Unspecified initial scalar state is unset, not zero; first adjustment asks for
a starting value. Unspecified checkbox state starts unselected. Requests enforce
capacity, type, role and snapshot block identity on the server. End/expiry follows
existing session cleanup. No long-term health/character storage is introduced.

Until those changes ship, Designer must describe unsupported interactive blocks
accurately and must not silently omit them from an otherwise eligible LiveSheet.
Decide the interactive release gate before production implementation.

## 6. Acceptance and decisions

Implementation requires a strict versioned schema, Python and browser validation,
shared layout fixtures, both editor controls, documentation and backward-compatibility
tests. No declared support until all targets have passed the same fixtures.

Owner review points:

1. Approve sheet-level basic LiveSheet interaction now, or printable blocks first?
2. Accept the neutral pattern line appearance and physical-spacing presets?
3. Accept blank template trackers with optional `Start: N` guidance?

Further general tables, measurement logs, persistent records, fillable PDFs,
formulas, arbitrary background layers, MusicXML import and multipage output are
explicitly outside this increment. They remain separate future decisions.

Research context: [MusicXML staff details](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/staff-details/)
offers terminology for staff lines and tuning, not an import dependency or a
claim of MusicXML conformance.
