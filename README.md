# Tafnit Automation

Prepare purchase requisitions in an existing, logged-in Tafnit Chrome session.
There are two workflows: the original **Rosh Electroptics quotations for
Thorlabs** parser and a [generalized local JSON/CSV workflow](Generalization/README.md)
for other registered suppliers. The generalized workflow prompts for supplier
details and leaves a saved draft by default; unfamiliar PDFs require reviewed
data rather than guessed extraction.

Both scripts attach the quotation, enter and verify the request, and leave
final approval to you. Neither script logs in or approves the final dialog.

## Choose a script

| | Rosh/Thorlabs | General quotations |
| --- | --- | --- |
| Entry point | `RoshElectroptics/rosh_thorlabs_tafnit.py` | `Generalization/tafnit.py` |
| Input | Supported selectable-text Rosh/Thorlabs USD PDF | The same supported PDF, or reviewed JSON/CSV plus the original PDF |
| Local profile | `RoshElectroptics/config.local.json` | `Generalization/config.local.json`; a different schema |
| Supplier | Thorlabs/Rosh codes from the profile | Supplier code/name, optional agent and website prompted on each new run |
| Start of live entry | Five-second countdown; no review confirmation prompt | Review shown in terminal; type the word `ENTER`, then a five-second countdown |
| Normal endpoint | Saves, creates customs declaration, requests final confirmation, stops | Saves and verifies a draft; customs depends on the profile |
| Final dialog | Requested automatically after verification; approval is manual | Requested only with `--open-final-confirmation`; approval is manual |

For other vendors, reviewed catalog configuration details, or explicit tax/unit
mappings, start with the [Generalization guide](Generalization/README.md).
The Rosh script retains catalog descriptions and verifies their part numbers;
Generalization also preserves differing quoted descriptions in line remarks.

## Quick start — Windows PowerShell

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/),
then clone this repository. Use Windows PowerShell and Windows Python for live
entry; WSL Python supports offline validation only. Substitute your checkout's
location below:

```powershell
cd D:\Workspace\Tafnit-Automation
uv sync --locked
uv run python -c "import os, sys; print(os.name); print(sys.executable)"
```

For desktop entry, the check must print `nt` and a Windows Python executable.
`uv run` uses the project environment; no manual activation is needed.
Use a separate checkout/environment for Linux or WSL validation rather than
reusing its `.venv` for Windows desktop entry.

For the Rosh workflow, create and fill its profile:

```powershell
if (!(Test-Path RoshElectroptics/config.local.json)) {
    Copy-Item RoshElectroptics/config.example.json RoshElectroptics/config.local.json
}
notepad RoshElectroptics\config.local.json
```

Fill in your own Tafnit settings; see [configuration](docs/CONFIGURATION.md).
The example intentionally cannot run live until its values are filled.

Validate a quotation without touching Tafnit:

```powershell
uv run RoshElectroptics/rosh_thorlabs_tafnit.py "D:\Orders\quotation.pdf" --dry-run
```

Compare the generated `quotation-tafnit/items.csv` and `review.json` with the
original PDF before starting live entry. These files are created beside the PDF.

For entry, leave the logged-in Tafnit home screen on display 1, complete the
[browser setup](RoshElectroptics/ROSH_THORLAB_TAFNIT.md#browser-setup), then run:

```powershell
uv run RoshElectroptics/rosh_thorlabs_tafnit.py "D:\Orders\quotation.pdf"
```

Both entry points follow **עברית → יזם → עברית → קליטה** and open the exact
**דרישה לרכש** (Purchase Request) menu option. An already-open blank
request is also supported. With `--resume`, reopen the original request first;
the scripts never open a new request during resume.

Omit the quotation path to use a file picker. Do not reuse an already placed
order. Leave the mouse and keyboard alone while entry is running.

For a local Generalization example with no PDF, profile or desktop access:

```powershell
uv run Generalization/tafnit.py --data Generalization/quotation.example.json --dry-run
```

Then follow the [Generalization setup and entry guide](Generalization/README.md)
to create its separate profile and prepare a real quotation. Move the pointer
to a screen corner or press Ctrl+C to interrupt either automation. See
[recovery](docs/TROUBLESHOOTING.md) before rerunning a stopped order.

## Documentation

- [General quotations: local extraction, reviewed data and vendor prompts](Generalization/README.md)
- [General quotation JSON/CSV format](Generalization/FORMAT.md)
- [Generalized form configuration](Generalization/CONFIGURATION.md)
- [Workflow, browser setup, and commands](RoshElectroptics/ROSH_THORLAB_TAFNIT.md)
- [Personal and institution configuration](docs/CONFIGURATION.md)
- [Stopping, recovery, and troubleshooting](docs/TROUBLESHOOTING.md)
- [Private data and public contributions](docs/PRIVACY.md)
- [Tests and development](docs/DEVELOPMENT.md)
- [Bundled GUI controller and templates](THIRD_PARTY_NOTICES.md)

```text
RoshElectroptics/
  rosh_thorlabs_tafnit.py     PDF parser and Tafnit workflow
  ROSH_THORLAB_TAFNIT.md     Workflow guide
  config.example.json       Blank public configuration
  config.local.json         Your settings — ignored, not distributed
  templates/                Ten generic UI crops, including home-menu controls
  _vendor/                  Bundled image-matching controller
Generalization/
  tafnit.py                 Vendor-independent reviewed-quotation entry point
  quotation.py              Local parsing, JSON/CSV and exact amount validation
  configuration.py          Institution/form mappings and supplier prompts
  desktop.py                Generalized adapter using existing GUI helpers
  workflow.py               Draft verification, recovery and manual handoff
  README.md                 Setup, commands, limits and recovery
docs/                       Setup, recovery, privacy, development
tests/                      Synthetic, offline regression tests
pyproject.toml              Dependencies
uv.lock                     Reproducible dependency versions
```

Desktop entry requires Windows, Chrome, and the supported Tafnit form layout.
PDF/JSON/CSV validation and offline tests also run on Linux/macOS. This is an independent
automation utility, not an official Tafnit, Rosh Electroptics, or Thorlabs product.
