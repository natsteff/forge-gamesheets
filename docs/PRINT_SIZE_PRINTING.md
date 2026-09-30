# Printing small FGS sheets

**Print size** sets the finished size of one sheet. Poker Card is 2.5 × 3.5 in;
Bridge Card is 2.25 × 3.5 in. **Page** selects the Letter or A4 base for Full
and Half Page. The **Orientation** control turns preset sizes, while Custom
Width and Height determine custom orientation directly. Print size is not saved
in `.fgs`; record a recommendation in Designer Notes and reselect it when the
file is opened again. The current small-format mode reflows sections without
reducing body type to miniature sizes. It does **not** proportionally shrink a
full-page design; unsupported or crowded content produces a fit warning.

## For an ordinary Letter/A4 printer

1. Choose the finished Print size and check that the preview fits. Long Header
   titles can wrap to two lines on cards; reduce content or choose a larger size
   if the preview warns that it cannot fit.
2. Open **Export → Arrange copies for printing**, choose printer paper and the
   number of copies, and leave **Cut guides** on if the sheets will be trimmed.
3. Read the output summary before export. It gives the PDF's paper orientation,
   copies per page, and page count. The layout may use landscape even when the
   individual card is portrait. For example, eight Poker Cards on Letter make
   two pages, six plus two, to retain safer printer margins.
4. In the PDF viewer's print dialog, select the stated paper **and orientation**,
   use **Actual size / 100%**, and turn off **Fit to page** or automatic scaling.
   If the printer still clips marks, check its non-printable margin setting;
   printer capabilities vary. Do not compensate by shrinking the sheet if its
   physical dimensions matter.

The arranged PDF preserves each finished sheet's dimensions. Its normal layout
keeps the finished sheet and outward cut guides at least 0.5 inch from the page
edge. It may use more than one printer page even when all copies could fit on a
borderless page.

## Direct finished-size PDF

**Export PDF** creates one PDF page at the selected finished size, without cut
guides or Letter/A4 placement. Use it for matching card stock or a printer that
supports that page size and edge-to-edge output. An ordinary printer may clip
content close to a card-sized page edge, even when the PDF itself is correct.
For ordinary Letter/A4 printing, use **Arrange copies for printing** instead.

## Borderless two-up Half Page

This option is enabled only when **Half Page** is selected and printer paper
matches the sheet's Letter/A4 base. Two halves then occupy the entire page with
no printer margin; a central cut guide can be included. Use it only if the
printer supports true borderless (edge-to-edge) printing. It is intentionally
unavailable for Poker Card, Bridge Card, and other print sizes.
