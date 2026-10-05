# Printing small FGS sheets

**Finished size** sets the physical size of one designed sheet. Poker Card is 2.5 × 3.5 in;
Bridge Card is 2.25 × 3.5 in. **Page** selects the Letter or A4 base for Full
and Half Page. The **Orientation** control turns preset sizes, while Custom
Width and Height determine custom orientation directly. FGS 1.4 saves selected
finished size and last-used print-sheet settings in `.fgs` after successful
print-sheet export, while allowing later changes.
Design a separate sheet for each
purpose—for example, a full-page rules sheet, half-page score sheet, and poker
reference card can all belong to the same game.

Full Page still uses its original one-page layout and overflow warning. Other
sizes compose content for the selected width, wrap headings and text, and then
uniformly fit the whole composition to one finished item if necessary. The
preview reports the fit percentage and approximate body-text size. It does not
enforce a legibility threshold: review the result and shorten or remove content
from that particular sheet if it is too small. Patterns and tracker marks also
change physical size when a composition is reduced.

## For an ordinary Letter/A4 printer

1. Choose the Finished size before composing the sheet. Review the fit percentage
   and apparent text size in the preview; headings may wrap across multiple lines.
2. Open **Export → Create print sheet**. Printer paper follows the sheet's Page
   setting unless you choose **Use different printer paper**. Select copies and
   Auto, Portrait, or Landscape orientation. Leave **Cut guides** on if trimmed.
3. Review the first arranged printer page and its output summary before export.
   Auto uses the fewest pages for the selected copies and prefers portrait on a tie.
   The summary gives the PDF's paper orientation, maximum copies per page, and
   page count. The layout may use landscape even when the
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
For ordinary Letter/A4 printing, use **Create print sheet** instead.

## Borderless two-up Half Page

This option is enabled only when **Half Page** is selected and printer paper
matches the sheet's Letter/A4 base. Two halves then occupy the entire page with
no printer margin; a central cut guide can be included. Use it only if the
printer supports true borderless (edge-to-edge) printing. It is intentionally
unavailable for Poker Card, Bridge Card, and other print sizes.
