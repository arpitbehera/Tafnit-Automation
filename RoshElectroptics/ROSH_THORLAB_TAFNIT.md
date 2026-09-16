# Rosh Electroptics / Thorlabs → Tafnit

`rosh_thorlabs_tafnit.py` reads a selectable-text Rosh Priority EX-WORK quotation
addressed to Thorlabs Inc., priced in USD, with PCS quantities and explicit
discounts. It checks consecutive rows, original and discounted unit prices,
extended amounts, and the printed total before desktop entry. Scanned PDFs,
other currencies, and unrecognized layouts cause a stop.

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
- The original PDF as an attachment, with a nonempty document description.
- One customs declaration, using this exact text for **both** description and
  intended use:

  > Optical components for use in an optics research laboratory

It saves the request, checks the live rows, total, header, and attachments,
then opens the final research-use confirmation. **It stops there.** No command
or option enables automatic final approval.

## Browser setup

1. Use Windows Python. Log in to Tafnit in Chrome, and open exactly one **new,
   blank purchase-request window** on display 1.
2. Use 2560×1440 display resolution, 100% Windows scaling, and 100% Chrome zoom.
   The script checks this setup because the bundled image crops depend on it.
3. Check that research group, requester, department, delivery location, and
   contact location match your [local configuration](../docs/CONFIGURATION.md).
   These are verified against the form's defaults; they are not silently changed.
4. Configure Chrome DevTools to open in a separate window: Ctrl+L, then
   Ctrl+Shift+J → DevTools three-dot menu → Dock side → Undock into separate
   window. Select Console, then close DevTools.

During entry the script opens Console briefly to read field values and locate
controls, closes it, then uses mouse and keyboard input. It uses your existing
login and does not collect passwords, cookies, or authentication tokens.

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

Optional arguments: `--config PATH` selects a private JSON profile;
`--budget-note "TEXT"` overrides its funding note for a new run;
`--state-dir PATH` selects the artifact directory. The default profile is
`config.local.json` beside the script, independent of the current directory.
A dry run works without a profile; supplier codes and funding note in the
review file will then be unspecified.

## Review and confirmation

By default the script creates `<PDF-name>-tafnit` beside the quotation. It
contains `items.csv`, `review.json`, a checkpoint, and screenshots from entry.
These contain private order information; keep them out of public repositories.

Tafnit may display three decimal places while the PDF rounds each line to two.
The script checks both totals using decimal arithmetic and the original prices;
it does not enter the already discounted unit price a second time.

When the terminal reports `STOPPED for your final confirmation`, inspect the
request and Tafnit's dialog, then confirm it yourself. If Tafnit displays a
validation error instead, resolve it manually. The automation makes no browser
inputs after its final submission action.

See [recovery instructions](../docs/TROUBLESHOOTING.md) for interrupted runs.
