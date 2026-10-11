# Subject labels (half A4)

Pastel notebook labels for **Economics, Accounting, English, Statistics and Git**, each exactly half an A4 sheet
(210 x 148.5 mm). The current design shows only the subject name (no write-in fields); the earlier version with
Name / Class / Section / Subject Teacher / School / Session lines is kept in `output/with-fields/`
(rebuild it with `--style fields`).

* `output/subject-labels-A4.pdf` - print this: A4 pages, two labels per page, dashed cut line in the middle.
  Print at **100% / Actual size** (not "Fit to page").
* `output/label-*.png` - each label on its own at 300 dpi (2480 x 1754 px).

Rebuild: `python3 build_labels.py` (needs Playwright + Chromium, Pillow, reportlab). Text for each label
(title, quote, book titles, checklist) is in `SUBJECTS` at the top of the script.

Fonts in `fonts/` are from Google Fonts (SIL Open Font License).
