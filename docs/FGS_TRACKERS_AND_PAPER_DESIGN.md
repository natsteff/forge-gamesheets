# Trackers and reusable paper — editor and delivery design

Status: **Original design rationale; implemented subset available locally for review.**

See [FGS 1.3](FGS_V1_3_SPECIFICATION.md) for the actual supported local contract.
Both local editors implement the new content. Docker Test and hosted Studio
remain unchanged until publication is approved. Personal health logs are deferred.

## Editor experience shared by FORGE GameSheets and Studio

Add **Tracker** and **Paper pattern** to the existing Add section selector.
Use existing button, input, label, focus, validation and undo/redo conventions.
Do not introduce native unstyled controls, another editor or another renderer.
Both products share field definitions/defaults and rendering rules; FORGE GameSheets retains
its autosave/workspace behavior and Studio retains browser-local export behavior.

### Paper-pattern controls

1. Pattern selector: Ruled, Square grid, Dot grid, Hex grid, Music staff, Tablature.
2. Optional Section title.
3. Size: Fill remaining page or Fixed height; music/tab show Number of staff
   groups instead of Fixed height. Switching patterns offers compatible defaults,
   preserves title/ID, and removes obsolete pattern-specific settings explicitly.
4. Relevant spacing / staff / string controls only; no irrelevant hidden saved fields.
5. Units preference: mm or inches for geometry, converted to canonical points once.
   This preference belongs to the editor, not document semantics.

Preset buttons provide sensible settings; show the actual resulting spacing
rather than an ambiguous label alone. Suggested presets: ruled 18/24/30 pt,
grid/dot/hex 14.25/18/28.25 pt, music line spacing 5 pt, tab line spacing 7 pt.
For hex paper explicitly label the size **Hexagon side length**, not grid spacing.
Music staff defaults to single; paired piano is a choice. Staff labels explain
that Number of groups counts one five-line staff or one paired piano group.

Fill is available only for a final full-width section. Explain disabled choices:
“Fill remaining page requires this section to be the last, full-width section.”
Moving, pairing, or inserting after a fill block must offer an explicit conversion
to its current fixed size/count, or Cancel; never reorder unrelated sections or
silently rewrite sizing. Imported invalid arrangements fail validation.

Preview status reports the generated result, for example “8 complete staves fit”
or “Grid spacing: 5.03 mm.” Overflow messages name the section and offer meaningful
changes: reduce count, use fill, reduce preceding content, or change orientation.
Never say Fits on one page when nothing could be generated.

### Tracker controls

- Section title / label.
- Appearance selector with a small neutral visual sample for each option.
- Capacity (label Number of boxes for boxes, Maximum value for current/maximum).
- Optional Starting value, with “Blank means no prescribed starting value.”
- Explanation: template marking spaces stay blank; starting value is guidance.

Default to current/maximum, capacity 10, no starting value. For capacities that
cannot fit a segmented bar, recommend current/maximum instead of making an
unusable tiny bar. Rename neither existing Checklist nor Notes; trackers represent
bounded state, checklists represent separately named tasks, and notes are blank text.

## New-sheet templates

Offer Blank sheet, Lined paper, Graph paper, Dot paper, Hex paper, Music manuscript,
Piano manuscript and Tablature. Each creates an ordinary document with one
full-width fill pattern, no mandatory rendered heading, and an editable document
title. Adding a heading is optional. No logo/footer defaults containing private data.

Do not replace the default New behavior without reviewing the existing FORGE GameSheets
workspace chooser and Studio confirmation flow. A template picker can extend those
flows while preserving unsaved-work protection. Choosing templates must not
require a game association or BGG lookup.

Useful mixed examples: practice goals + blank music; instructions + graph area;
character title + Health / Mana trackers; turn reference + ammunition boxes.
Use invented labels and values only, never real medical data or branded character art.

## Interactive proposal

If the owner approves basic LiveSheet interaction, expose current/maximum through
labeled decrement, numeric entry and increment controls. Expose checkboxes through
accessible toggle controls; numbered boxes/bar map to one scalar value. Do not rely
on color alone; show counts and meaningful accessible labels. Keyboard and mobile
use must be tested. Ordinary printed templates contain no buttons.

Sheet-level authorization is the starting recommendation, not an assumption that
every participant can edit another person's tracker. Independent per-player
trackers are a future ownership design. Preserve values across refresh and keep
reset explicit; old running sessions do not change when the template is edited.
Paper patterns are static, with no interactive ink layer.

## Delivery sequence

1. Owner review of draft and three decisions listed in the specification.
2. Formalize the additive format schema and profile revision with fixtures.
3. Implement shared pattern primitives and fixed/fill allocation. Include all
   six patterns in the approved paper milestone, including music and tablature;
   do not label music complete after only shipping grids.
4. Implement shared tracker rendering and both editors; coordinate exports,
   undo/redo, imports, version promotion, validation, autosave and reload.
5. If approved, implement scoped LiveSheet state/eligibility alongside trackers;
   otherwise document the printable-only limitation and defer the interactive gate.
6. Update README/spec support matrix and safe example screenshots; perform owner
   review locally before any requested commit/push/hosted-site publication.

Reuse the current PDF pipeline. Lines, circles and text should be generated as
vector display-list operations. Audit current SVG/PDF primitive support before
adding operations; use the same geometry for both outputs. No PDF-generator
replacement is assumed or warranted by this design.

## Required verification matrix

| Area | Required checks |
| --- | --- |
| Compatibility | 1.0–1.2 fixtures unchanged; strict future-version rejection; no silent data loss/version downgrade |
| Validation | Unknown properties, invalid settings/types/counts, NaN/infinity, duplicate IDs, fill placement, parser/resource limits |
| Patterns | All six types, fixed/fill, complete staff/hex groups, label gutters, nonzero fit, no boundary overflow |
| Pages | Letter/A4, both orientations, title/no title, footer/no footer, paired fixed sections |
| Geometry | Exact physical spacing, deterministic hex coordinates, deduplicated edges, same SVG/PDF display list |
| Trackers | All four appearances, bounds, wrapping, unset versus zero, starting guidance, large-capacity errors |
| Editors | Identical defaults, styled controls, keyboard labels, undo/redo, duplicate ID regeneration, save/import/export/reload |
| LiveSheet if approved | Tracker-only readiness, host/scorer permissions, malformed state, independent checkbox/scalar semantics, snapshot isolation, refresh/reset/expiry |
| Privacy | No runtime values in reusable FGS; no health history promises; no diagnostic coloring; safe sample data |
| Performance | Maximum supported pattern density and block count, bounded drawing operations, malicious tiny spacing / huge counts |

For performance, implementation must set and document a per-document drawing-operation
budget shared by both consumers. Exceeding it produces a clear validation/fit failure,
not unbounded work. Select a tested budget before marking the profile normative.

Documentation-only work does not alter application behavior or support claims.
Implementation must pass narrow regressions, the complete available suite/lint,
shared-renderer tests, Studio tests and representative local visual/PDF review.

## Deferred deliberately

General measurement-log tables and fields, persistent health/character records,
medical interpretation, arbitrary formulas, editable notation, MusicXML import,
custom background layers, multipage documents and fillable PDF widgets. Keep those
visible as future opportunities, but do not pull them into this milestone.
