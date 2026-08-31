# 001 — Browser PDF printing is not tracked

Forge GameSheets records successful PDF views and downloads. It does not expose
a separate Print action while PDFs are served through the browser's built-in PDF
viewer.

A Print link would currently open the same PDF as View, and the application
cannot reliably detect whether the browser subsequently completed a print job.
Users print from the PDF viewer or with the browser's print command. Explicit
print history can be added later only with a distinct, reliable print workflow.
