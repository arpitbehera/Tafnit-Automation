# General quotations → Tafnit drafts

`tafnit.py` prepares a purchase-request **draft** for a registered supplier from
locally reviewed quotation data. It prompts for the Tafnit supplier code, the
exact supplier name displayed by Tafnit, an optional agent code, and an optional
supplier website fallback. It then
enters the items and checks the saved request against the reviewed data.

**Final approval is always yours.** By default the script never clicks the
submission button. `--open-final-confirmation` can open the final dialog after
verification, but cannot approve it. That option requires mappings for net,
tax and gross totals. The original Rosh script remains available unchanged.

## Why there is a reviewed data format

Supplier-independent entry is useful; an unattended parser claiming to
understand every PDF is not reliable. Layouts, currencies, taxes, freight,
discounts, units and scanned pages vary. This implementation separates:

1. **Extraction:** the existing validated Rosh/Thorlabs parser handles its known
   quotation format. Other PDFs produce local extracted text and editable
   JSON/CSV templates, then stop without touching Tafnit.
2. **Review:** supply the vendor-independent [quotation format](FORMAT.md),
   compare it with the PDF, and validate exact amounts locally.
3. **Entry:** the script prompts for supplier details, verifies Tafnit's resolved
   supplier, enters the approved data, saves, and reads back the result.

No document is sent to an AI service, OCR service or external extraction API.
There is no cloud fallback. Scans need local transcription or your own local OCR
followed by review. A registered supplier alone does not guarantee that a
different Tafnit request type or form layout is supported.

## First-time setup

Use Windows Python 3.11+, the repository's existing `uv` dependencies, and the
same Chrome/display setup as the [original workflow](../RoshElectroptics/ROSH_THORLAB_TAFNIT.md#browser-setup):
2560×1440, 100% Windows scaling and Chrome zoom, display 1, undocked DevTools
Console, and an existing login. Offline validation also works on Linux/macOS.

From the repository root in PowerShell:

```powershell
uv sync --locked
# Run this copy only if you have not already created your local profile.
Copy-Item Generalization/config.example.json Generalization/config.local.json
notepad Generalization/config.local.json
```

Fill the institution defaults, funding note, appropriate item classification
and customs description/use. Follow [configuration and form mappings](CONFIGURATION.md).
The blank example intentionally cannot operate Tafnit. It contains the known
foreign/USD codes, not universal domestic/currency/tax settings. Do not copy
the old Rosh JSON directly: the generalized configuration has a different shape.

## Try local validation

The shipped example is synthetic and does not need a PDF or local config:

```powershell
uv run Generalization/tafnit.py --data Generalization/quotation.example.json --dry-run
```

For an actual quotation:

```powershell
uv run Generalization/tafnit.py "D:\Orders\quotation.pdf" --dry-run
```

For an unknown layout this exits with code `2` and creates:

```text
quotation-general-tafnit/
  extracted.local.txt              Local PDF text, or a scan notice
  quotation.template.local.json    Header/totals template; items initially []
  items.template.csv               Item column headers
```

Fill the JSON including its `items`, or keep `items: []` and fill the CSV.
Templates are never overwritten on later attempts. Do not put guessed values
in a missing field merely to pass validation. Consult the PDF/vendor instead.

```powershell
# JSON with embedded items
uv run Generalization/tafnit.py "D:\Orders\quotation.pdf" --data "D:\Orders\quotation.local.json" --dry-run

# JSON headers/totals plus CSV items
uv run Generalization/tafnit.py "D:\Orders\quotation.pdf" --data "D:\Orders\quotation.local.json" --items-csv "D:\Orders\items.csv" --dry-run

# Also validate that your profile maps this currency, units and taxes
uv run Generalization/tafnit.py "D:\Orders\quotation.pdf" --data "D:\Orders\quotation.local.json" --dry-run --config Generalization/config.local.json
```

Dry-run writes `quotation.review.local.json` and `items.review.csv`, but no
checkpoint, supplier prompt or desktop operation. It requires a PDF or `--data`
path; it never opens a picker. Without an explicit `--config`, it validates the
quotation only. It does not prove the PDF and JSON describe the same goods;
compare them yourself. Input files cannot occupy generated output paths.

## Enter a draft

Open one **new blank** purchase request with the configured institution defaults.
Run the same command without `--dry-run`:

```powershell
uv run Generalization/tafnit.py "D:\Orders\quotation.pdf" --data "D:\Orders\quotation.local.json"
```

The script asks for:

- The registered **Tafnit supplier code**, not the company's tax/VAT number.
- The exact supplier name shown by Tafnit's lookup. This may differ in spelling
  or language from the quotation; verify they are the same invoice recipient.
- An agent code, or blank if no agent applies.
- A full supplier website URL to use when neither the catalog nor an item's
  reviewed `website` supplies a link. Leave it blank only when those links are
  available; the script stops before saving a row with no website.

It shows every item, amount, funding note and relevant profile choices. Type
the word `ENTER` to start. Any other response cancels before desktop entry.
Supplier lookup must resolve to the entered name/code/agent before item entry.
Unknown vendors are not registered automatically.

Tafnit can require a website even for catalogued items. Existing catalog links
are preserved; missing links use the item's reviewed URL, then the supplier
fallback. Known Rosh imports derive the Thorlabs product URL locally. Generic
imports never guess a vendor's URL. Descriptions containing `≥`, `≤` or `Ø`
are entered as `>=`, `<=` or `dia. ` to survive Tafnit's legacy text storage;
the original quotation text remains in the review data, and the terminal shows
the entry version when it differs.

Quoted descriptions are preserved for catalogued items too, including variant
details when several rows share a supplier part number. Editable descriptions
receive the quoted text. When Tafnit locks a catalog description, the manufacturer
part must match exactly; a differing description is retained and the quote text
is stored in that line's remarks. Verification opens the saved line to check its
catalog identity and exact quotation remarks, including after a page save and on
resume. Missing, altered or unwritable remarks stop the run. Older drafts with
different catalog descriptions and no matching quotation remarks still stop.

Do not operate the mouse or keyboard during automation. The script attaches
the PDF, enters rows with reviewed unit prices and discounts, optionally creates
the configured customs document, saves the draft, and verifies its content.
If tax/gross readback is not mapped for a zero-tax quote, those totals are
explicitly marked **UNVERIFIED** in the terminal and checkpoint; inspect them
manually. Nonzero quoted tax requires both readback mappings before entry.

If you have verified all total-field mappings and want the script to open the
final research-use dialog after its checks:

```powershell
uv run Generalization/tafnit.py "D:\Orders\quotation.pdf" --data "D:\Orders\quotation.local.json" --open-final-confirmation
```

It records the handoff attempt before clicking `KUPDT`, then takes a screenshot
and stops. `STOPPED after requesting final confirmation` means you must inspect
Tafnit's confirmation **or validation message**; it does not prove the dialog
opened or the request was submitted. No flag accepts that dialog, presses Enter
there, or retries its opening. This boundary assumes the current Tafnit `KUPDT`
behavior still requires a separate final confirmation.

## Recovery and limits

Move the pointer to a screen corner or press Ctrl+C to stop. A partial draft
may remain; there is no rollback. Inspect Tafnit before running again:

```powershell
uv run Generalization/tafnit.py "D:\Orders\quotation.pdf" --data "D:\Orders\quotation.local.json" --resume
```

Use the same PDF, data, profile and `--state-dir`/CSV arguments. Resume reuses
the checkpoint's supplier, checks hashes of the PDF and all normalized input,
then checks the live request number, header and item rows. A changed item,
profile or supplier blocks resume before GUI initialization. Missing previously
saved rows or an unrelated attachment blocks data entry. A row accepted just
before an interruption is recognized from the live table and is not duplicated.

A saved draft can be resumed with `--open-final-confirmation` if its original
profile already included all total mappings. Once the final handoff is recorded,
resume is blocked even if the click failed. Finish manually; do not delete the
checkpoint to bypass it. If you intentionally change the data/profile mid-run,
finish or correct the existing draft manually rather than starting a duplicate.

Existing reviewed JSON/CSV files without website fields remain valid, and their
checkpoints retain the same input fingerprint. A new nonempty website is an
input change and is checked on resume. Known Rosh automatic parsing now adds
product URLs and recognizes `(UK)` source notes: to resume an older automatic
run, use a separate copy of its original `quotation.review.local.json` with
`--data` and the original `--state-dir`, or finish the existing draft manually.
If older descriptions were already corrupted to `?`, correct the draft manually;
the verifier does not accept the corrupted text as equivalent.

The adapter supports the observed 12-column Tafnit form. Different domestic,
service, capital-equipment or tax workflows need verified local mappings and
may require adapter changes. One classification is used for all uncatalogued
rows. Budget-number workflows, mixed currencies, credits, negative adjustment
rows and order-level discounts are not automatically handled. See [FORMAT.md](FORMAT.md).
Its [diagnostic guide](FORMAT.md#diagnosing-an-unfamiliar-quotation) explains how
to check currency changes and footer adjustments before filling blank templates.
Customs reuse verifies the attachment's presence/title and this run's checkpoint,
not the downloaded document's bytes; do not replace it between runs.

Offline tests cover parsing, validation, simulated entry and recovery. An assisted
live draft verified the foreign-USD field mappings and catalog-remarks approach.
The updated automated catalog path has offline regression coverage, but has not
yet completed an unattended live run. No institution-wide vendor registry or
procurement policy is assumed. Check the first saved draft carefully, including
catalog-selected items and totals.

## Options, files and privacy

`--config PATH` selects another profile; `--state-dir PATH` selects the artifact
directory. Omit the PDF for a file picker during entry. Both direct script and
`uv run python -m Generalization.tafnit` invocation work. Exit codes: `0` for
success/cancellation, `1` for a validation/entry stop, `2` for review templates
or command-line usage errors. `--help` lists all options.

Keep quotations, profiles, CSVs, checkpoints and screenshots private. Use
`*.local.json` for reviewed input inside the repository; it is ignored. The
default `*-general-tafnit` artifact directory is also ignored. Custom artifact
locations should stay outside the repository. Browser login is reused; no
password, session token or API key is read. Tafnit receives normal browser
requests when fields are entered and documents uploaded.

Developer notes: [DESIGN.md](DESIGN.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
