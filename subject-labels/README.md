# Subject labels (half A4)

Pastel notebook labels for **Economics, Accounting, English and Statistics**, each exactly half an A4 sheet
(210 x 148.5 mm), with blank lines for Name, Class, Section, Subject Teacher, School and Session.

* `output/subject-labels-A4.pdf` - print this: 2 A4 pages, two labels per page, dashed cut line in the middle.
  Print at **100% / Actual size** (not "Fit to page").
* `output/label-*.png` - each label on its own at 300 dpi (2480 x 1754 px).

Rebuild: `python3 build_labels.py` (needs Playwright + Chromium, Pillow, reportlab). Text for each label
(title, quote, book titles, checklist) is in `SUBJECTS` at the top of the script.

Fonts in `fonts/` are from Google Fonts (SIL Open Font License).
