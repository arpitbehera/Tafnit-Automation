# Tafnit Automation

Prepare purchase requisitions in an existing, logged-in Tafnit Chrome session.
There are two workflows: the original **Rosh Electroptics quotations for
Thorlabs** parser and a [generalized local JSON/CSV workflow](Generalization/README.md)
for other registered suppliers. The generalized workflow prompts for supplier
details and leaves a saved draft by default; unfamiliar PDFs require reviewed
data rather than guessed extraction.

The original Rosh automation enters and verifies the order, attaches the quotation, creates
the customs declaration, saves the request, and opens the final confirmation.
**The user must approve that final confirmation. The script never approves it.**

## Quick start — Windows PowerShell

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/),
then clone this repository and run:

```powershell
cd D:\Workspace\Tafnit-Automation
uv sync --locked
Copy-Item RoshElectroptics\config.example.json RoshElectroptics\config.local.json
notepad RoshElectroptics\config.local.json
```

Fill in your own Tafnit settings; see [configuration](docs/CONFIGURATION.md).
Skip the copy command if your local configuration already exists.

Validate a quotation without touching Tafnit:

```powershell
uv run RoshElectroptics/rosh_thorlabs_tafnit.py "D:\Orders\quotation.pdf" --dry-run
```

For entry, open a new blank Tafnit requisition on display 1, complete the
[browser setup](RoshElectroptics/ROSH_THORLAB_TAFNIT.md#browser-setup), then run:

```powershell
uv run RoshElectroptics/rosh_thorlabs_tafnit.py "D:\Orders\quotation.pdf"
```

Omit the quotation path to use a file picker. Do not reuse an already placed
order. Leave the mouse and keyboard alone while entry is running.

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
  templates/                Six generic UI crops
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
