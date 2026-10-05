# FGS 1.4 specification

Status: Implemented locally; publication is verified separately.

FGS 1.4 extends [FGS 1.3](FGS_V1_3_SPECIFICATION.md) without changing sheet content or the [FGS 1.3 Page Rendering Profile](FGS_PAGE_RENDERING_PROFILE_1_3.md). It adds optional, portable print defaults. Readers accept versions 1.0–1.4; older files remain valid. These fields require `format_version: "1.4"` and are omitted unless selected. Unknown ordinary properties remain invalid. The structural schema is [fgs-v1.4.schema.json](schemas/fgs-v1.4.schema.json).

`page.size` (`letter` or `a4`) and `page.orientation` (`portrait` or `landscape`) were already stored in earlier FGS versions. FGS 1.4 adds optional `page.finished_size`:

```json
"finished_size": {"preset": "half"}
```

The `preset` is `full`, `half`, `poker`, `bridge`, or `custom`. The first four permit no other properties. A custom size also requires numeric `width`, numeric `height`, and `unit` (`in` or `cm`); each dimension must be 0.5–14 inches (1.27–35.56 cm). For custom sizes, width and height directly determine orientation. If omitted, finished size is Full Page. An explicit export choice overrides the stored default for that export.

The optional top-level `print_sheet` object stores suggested settings for arranging copies on printer paper:

```json
"print_sheet": {"paper": "inherit", "orientation": "auto", "copies": 2, "cut_guides": true, "borderless": false}
```

`paper`, `copies`, `cut_guides`, and `borderless` are required when the object is present. `paper` is `inherit`, `letter`, or `a4`; `inherit` follows the document's `page.size`. `copies` is an integer from 1 to 48; `cut_guides` and `borderless` are booleans. Optional `orientation` is `auto` (the default), `portrait`, or `landscape`. Auto chooses the orientation that uses the fewest pages for the requested copies, preferring portrait on a tie. A manual orientation must fit the finished sheet or export fails without clipping. The actual printer-sheet placement is derived, not stored.

If `print_sheet` is omitted, editors begin with inherited paper, Auto orientation, one copy, cut guides on, and borderless off. Opening or canceling the print-sheet dialog does not add the object. A successful print-sheet export records the last-used choices; later exports can change them. These settings are not a command to print or a claim that the target printer supports borderless output. Borderless two-up remains available only for a matching Half Page and printer paper.
