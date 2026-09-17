# General quotations → Tafnit drafts

`tafnit.py` prepares a purchase-request **draft** for a registered supplier from
locally reviewed quotation data. It prompts for the Tafnit supplier code, the
exact supplier name displayed by Tafnit, an optional agent code, and an optional
supplier website fallback. It then
enters the items and checks the saved request against the reviewed data.

**Final approval is always yours.** By default the script never clicks the
submission button. `--open-final-confirmation` can open the final dialog after
verification, but cannot approve it. That option requires mappings for net,
tax and gross totals. The Rosh script remains available with its own supplier
logic and automatic final-dialog handoff; both entry points share home-screen
startup and low-level desktop helpers.

## Why there is a reviewed data format

Supplier-independent entry is useful; an unattended parser claiming to
understand every PDF is not reliable. Layouts, currencies, taxes, freight,
discounts, units and scanned pages vary. This implementation separates:

1. **Extraction:** the existing validated Rosh/Thorlabs parser handles its known
   quotation format. Readable PDFs with unsupported layouts produce local
   extracted text and editable JSON/CSV templates, then stop without touching Tafnit.
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
if (!(Test-Path Generalization/config.local.json)) {
    Copy-Item Generalization/config.example.json Generalization/config.local.json
}
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

The directory is beside the PDF. Unreadable/encrypted PDFs can fail extraction
with exit `1` before templates are created. Use a readable local copy or prepare
reviewed `--data` yourself; with `--data`, the PDF is attached without automatic
quotation extraction.

Fill the JSON including its `items`, or keep `items: []` and fill the CSV.
Templates are never overwritten on later attempts. Do not put guessed values
in a missing field merely to pass validation. Consult the PDF/vendor instead.
For example, copy `quotation.template.local.json` to
`D:\Orders\quotation.local.json`, and, if using CSV, copy `items.template.csv`
to `D:\Orders\items.csv`. Fill those copies before running the examples below.

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
quotation only, even when `Generalization/config.local.json` already exists.
It does not prove the PDF and JSON describe the same goods;
compare them yourself. Input files cannot occupy generated output paths.
`--dry-run` cannot be combined with `--resume` or `--open-final-confirmation`.

## Enter a draft

Log in to Tafnit in Chrome and leave its **home screen** as the active tab on
display 1. Keep one eligible Tafnit home window or one purchase-request window;
multiple purchase-request windows stop startup.
The script follows **עברית → יזם → עברית → קליטה** and opens the exact
**דרישה לרכש** (Purchase Request) menu option. Allow Tafnit popups in Chrome.
An already-open **new blank** purchase request is also supported and takes
precedence over the home screen. The form must have the configured institution
defaults. See [browser setup](../RoshElectroptics/ROSH_THORLAB_TAFNIT.md#browser-setup)
for menu, display and DevTools requirements.
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
the word `ENTER` to start, rather than just pressing the Enter key. Any other
response cancels before desktop entry. A five-second countdown follows your
confirmation. Resume also shows the review and requires typing `ENTER` again.
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

On normal completion, the terminal reports `Saved draft <number>`. Review that
request in Tafnit and finish it manually, or use the
[saved-draft resume command](#recovery-and-limits) if the original profile
already includes all total-field mappings.

For a **new run**, if you have verified all total-field mappings and want the
script to open the final research-use dialog after its checks:

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
may remain; there is no rollback. Inspect Tafnit before running again.

Keep or reopen the **same request** before `--resume`. Resume never opens a new
request from the home screen, including after a startup interruption. If no form
was opened before the interruption, manually open **דרישה לרכש** and inspect
its blank form before resuming.

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
profile already included all total mappings:

```powershell
uv run Generalization/tafnit.py "D:\Orders\quotation.pdf" --data "D:\Orders\quotation.local.json" --resume --open-final-confirmation
```

Also repeat any original `--items-csv`, `--config` and `--state-dir` arguments.
Once the final handoff is recorded,
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
yet completed an unattended live run. Home-screen startup is tested with
simulated windows/DOM and has not been verified against a live logged-in home
screen. No institution-wide vendor registry or procurement policy is assumed.
Check the first saved draft carefully, including
catalog-selected items and totals.

## Options, files and privacy

| Argument | Behavior |
| --- | --- |
| `pdf` | PDF attachment path. Live entry always needs a PDF; omitting the path opens a file picker even when `--data` is supplied. Cancelling exits. |
| `--data PATH` | Reviewed quotation JSON. Without it, try the known Rosh PDF parser and emit review templates if the layout is unsupported. |
| `--items-csv PATH` | Reviewed item CSV; requires `--data` whose `items` array is empty. |
| `--dry-run` | Validate/export locally; requires an explicit PDF or `--data`. No picker, supplier prompt, checkpoint creation or desktop entry. Cannot be combined with resume or final-confirmation flags. |
| `--config PATH` | Generalized profile. Live entry defaults to `Generalization/config.local.json` beside the script. Dry-run checks a profile only when this flag is explicit. |
| `--state-dir PATH` | Output/checkpoint directory; see defaults below. Repeat this argument on resume. |
| `--resume` | Use the existing checkpoint, stored supplier and original open request; recheck input/profile and ask for `ENTER` again. |
| `--open-final-confirmation` | After verifying the saved draft, request the final dialog and stop. Requires all total mappings; it never approves the dialog. |
| `--help` | Print usage and exit. |

By default, artifacts go to `<PDF-stem>-general-tafnit` beside the PDF. A
data-only dry run uses `<JSON-stem>-general-tafnit` beside its JSON input.
`--state-dir` overrides both. A successful dry run writes
`quotation.review.local.json` and `items.review.csv`; accepted live entry also
creates `state.json` before desktop startup and screenshots as the run proceeds.
Review exports can be replaced on subsequent runs; extraction templates are
preserved. A stopped startup can have a checkpoint without a saved request.
Check [recovery](../docs/TROUBLESHOOTING.md) before choosing whether to resume.

Do not use a generated review file as input at the same output location: copy
it elsewhere first, keeping the original `--state-dir` if resuming. The script
rejects collisions to protect source inputs from being overwritten.

Both direct script and `uv run python -m Generalization.tafnit` invocation work
from the repository root. Exit codes: `0` for success/cancellation, `1` for a
handled validation/entry stop, `2` for review templates or command-line usage
errors. Run `uv run Generalization/tafnit.py --help` for the current option list.

Keep quotations, profiles, CSVs, checkpoints and screenshots private. Use
`*.local.json` for reviewed input inside the repository; it is ignored. The
default `*-general-tafnit` artifact directory is also ignored. Custom artifact
locations should stay outside the repository. Browser login is reused; no
password, session token or API key is read. Tafnit receives normal browser
requests when fields are entered and documents uploaded.

Developer notes: [DESIGN.md](DESIGN.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
