# Rosh Electroptics / Thorlabs → Tafnit

`rosh_thorlabs_tafnit.py` reads a selectable-text Rosh Priority EX-WORK quotation
addressed to Thorlabs Inc., priced in USD, with PCS quantities and explicit
discounts. It checks consecutive rows, original and discounted unit prices,
extended amounts, and the printed total before desktop entry. Scanned PDFs,
other currencies, and unrecognized layouts cause a stop.

Complete the [Windows environment setup](../README.md#quick-start--windows-powershell)
and fill the [Rosh local profile](../docs/CONFIGURATION.md) before live entry.
This script does not accept reviewed JSON/CSV input; for that, use
[Generalization](../Generalization/README.md).

## What it enters

- Foreign purchase request, procurement, USD; supplier Thorlabs and agent Rosh
  Electroptics using the codes in your private configuration.
- Your configured funding note; the budget-number field must be blank.
- Quotation number/date, vendor reference, payment terms, and available weight.
  The packaging note says dimensions are not provided; inspect that note if
  your quotation does specify dimensions.
- Each part's quantity, original unit price, and separate discount. Catalog
  lookup happens before prices, and catalog descriptions are retained.
  Uncatalogued items use the PDF description and classification Scientific
  Equipment / Laboratory Instruments.
- Missing item websites use a locally constructed Thorlabs product URL.
  Uncatalogued descriptions replace `≥`, `≤` and `Ø` with `>=`, `<=` and
  `dia. ` for Tafnit's legacy text storage; review exports retain the source text.
- The original PDF as an attachment, with a nonempty document description.
- One customs declaration, using this exact text for **both** description and
  intended use:

  > Optical components for use in an optics research laboratory

It saves the request, checks the live rows, total, header, and attachments,
then opens the final research-use confirmation. **It stops there.** No command
or option enables automatic final approval.

Catalog rows are verified by part number and amounts; their catalog description
can differ from the quotation. If a quoted length, connector or other variant
must be retained, use the generalized workflow's description/remarks checks.
This script does not configure tax or verify separate net/tax/gross fields.
It compares Tafnit's `NetoDollar` total with the entered item total, so an added
tax amount causes a stop. Use a verified generalized profile for taxed quotes.

## Browser setup

1. Use Windows Python. Log in to Tafnit in Chrome, and leave its **home screen**
   as the active tab on display 1. Keep only one purchase-request window open;
   when starting from home, keep one Tafnit home window. The script follows
   **עברית → יזם → עברית → קליטה** and
   selects exactly **דרישה לרכש** (Purchase Request).
   Allow Tafnit popups in Chrome. An already-open **new, blank purchase-request
   window** is also supported and takes precedence over the home screen.
   If the home-window title contains only your institution name, keep it as the
   only Chrome window so the script can select it and verify its hostname.
2. Use 2560×1440 display resolution, 100% Windows scaling, and 100% Chrome zoom.
   The script checks this setup because the bundled image crops depend on it.
3. Check that research group, requester, department, delivery location, and
   contact location match your [local configuration](../docs/CONFIGURATION.md).
   These are verified against the form's defaults; they are not silently changed.
4. Configure Chrome DevTools to open in a separate window: Ctrl+L, then
   Ctrl+Shift+J → DevTools three-dot menu → Dock side → Undock into separate
   window. Select Console, then close DevTools.

The new form must have no saved request number and status **New**. The menu
option **דרישה לרכש** is distinct from the foreign-request type selected inside
the form. Similar menu names are not accepted. No separate `kalirkosh.py`
installation or credentials file is needed; the navigation assets are bundled.

During entry the script opens Console briefly to read field values and locate
controls, closes it, then uses mouse and keyboard input. It uses your existing
login and does not collect passwords, cookies, or authentication tokens.

The menu sequence and its four bundled image crops come from `kalirkosh.py`.
Once the menu is expanded, the script reads its controls to require one exact
**דרישה לרכש** label. A missing template or missing/ambiguous label stops entry.
It clicks that option once, waits for its window (or navigation in the same
window), and checks the purchase-request title, configured host and new blank
form before entering details. It does not log in for you.

For `--resume`, keep or reopen the **original request**, even if the previous
run stopped during startup. Resume never opens a replacement request from the
home screen. If startup stopped before opening a form, open **דרישה לרכש**
manually and inspect it before resuming.

## Commands

Run these from the repository root in Windows PowerShell:

```powershell
# Validate and write review files; no desktop actions
uv run RoshElectroptics/rosh_thorlabs_tafnit.py "D:\Orders\quotation.pdf" --dry-run

# Enter a new request
uv run RoshElectroptics/rosh_thorlabs_tafnit.py "D:\Orders\quotation.pdf"

# Choose a PDF interactively
uv run RoshElectroptics/rosh_thorlabs_tafnit.py

# Continue the same interrupted request after inspecting it
uv run RoshElectroptics/rosh_thorlabs_tafnit.py "D:\Orders\quotation.pdf" --resume

# See all options
uv run RoshElectroptics/rosh_thorlabs_tafnit.py --help
```

**Review the dry-run exports before running without `--dry-run`.** Live entry
starts automatically after a five-second countdown; this script does not ask
you to type `ENTER`. The countdown also applies on resume.

| Argument | Behavior |
| --- | --- |
| `pdf` | PDF path; omit it to open a file picker, including in dry-run mode. Cancelling the picker exits. |
| `--dry-run` | Parse/check the PDF and write `items.csv` and `review.json`; do not operate Tafnit or create a checkpoint. Pass a PDF path to avoid any file picker. |
| `--config PATH` | Rosh JSON profile; defaults to `config.local.json` beside this script, independent of the working directory. |
| `--budget-note "TEXT"` | Override the profile's funding note. If used for a run, pass the same override on resume. |
| `--state-dir PATH` | Artifact/checkpoint directory; defaults to `<PDF-stem>-tafnit` beside the PDF. Use the same directory on resume. |
| `--resume` | Continue the checkpoint for this PDF using its original open request. It never opens a new request. |
| `--help` | Print usage and exit. |

A dry run loads and validates the selected profile if that file exists. If it
does not exist, PDF validation can proceed without it; supplier codes are null
and the funding note is blank unless overridden. An existing but incomplete
profile still fails validation. A dry run does not verify live browser fields.
Use `--dry-run` separately from `--resume`: dry-run returns before checkpoint
checks, even if both flags are supplied.

To use custom locations, keep the same arguments when adding `--resume` later:

```powershell
uv run RoshElectroptics/rosh_thorlabs_tafnit.py "D:\Orders\quotation.pdf" --config "D:\Private\rosh.local.json" --state-dir "D:\Orders\quotation-run" --budget-note "Approved funding note"
```

`uv run python -m RoshElectroptics.rosh_thorlabs_tafnit` also works from the
repository root with the same arguments. Normal exit codes are `0` for a
successful dry run, completed handoff or picker cancellation, `1` for a handled
validation/automation stop, and `2` for command-line usage errors. A successful
handoff does not mean the order was finally approved.

## Review and confirmation

By default the script creates `<PDF-stem>-tafnit` beside the quotation. It
contains `items.csv` and `review.json`. Live entry adds `state.json` before
desktop startup and screenshots as entry progresses; a startup failure may
therefore leave a checkpoint without a screenshot or request number.
Review exports are replaced on later invocations after successful PDF parsing.
These contain private order information; keep them out of public repositories.

Tafnit may display three decimal places while the PDF rounds each line to two.
The script checks both totals using decimal arithmetic and the original prices;
it does not enter the already discounted unit price a second time.

When the terminal reports `STOPPED after requesting final confirmation`, inspect
the request and Tafnit's dialog, then confirm it yourself. If Tafnit displays a
validation error instead, resolve it manually. The checkpoint records the
handoff attempt, not successful submission. The automation makes no browser
inputs after that action.

See [recovery instructions](../docs/TROUBLESHOOTING.md) for interrupted runs.
