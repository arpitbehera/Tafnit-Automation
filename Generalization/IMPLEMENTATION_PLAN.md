# General Tafnit Implementation Plan

**Goal:** Prepare vendor-independent requisitions from locally reviewed quotes.

**Architecture:** Separate local extraction/normalization, explicit form
configuration, desktop entry, and CLI orchestration. Reuse low-level Rosh GUI
helpers without changing the original workflow.

**Tech stack:** Python 3.11+, stdlib, existing pypdf and Windows GUI dependencies.

**Spec:** [DESIGN.md](DESIGN.md).

## Constraints

- Local processing only; no API keys, cloud extraction, or network clients.
- No final approval; record handoff before optionally opening its dialog.
- Default live endpoint is a saved draft, with no submission click.
- Tests use synthetic data and never operate Tafnit.
- Changes remain reviewable in the requested workspace.

## Tasks

1. [x] Implement quotation validation and local extraction with tests first.
   Files: `quotation.py`, `quotation.example.json`, `tests/test_generalization.py`.
   Interface: `parse_quotation(data) -> Quotation`, `load_quotation(path, csv_path)`.
   Check exact row math, summed amounts, taxes, dates, currencies, precision,
   malformed input, CSV columns, duplicate JSON keys and unsupported layouts.
   Run `uv run --locked python -m unittest discover -s tests -v`.
2. [x] Implement validated configuration and supplier prompts with tests first.
   Files: `configuration.py`, `config.example.json`, shared tests.
   Interface: `load_config(path) -> Config`, `validate_mapping(quote, config)`.
   Reject missing codes, unknown units, tax without readback and blank names.
3. [x] Implement desktop adapter and checkpointed workflow with tests first.
   Files: `desktop.py`, `workflow.py`, shared tests.
   Verify resolved vendor, units, currency, classification and row prices;
   resume from live rows, avoid duplicate attachments, and default to draft.
   Exercise success, mismatch, failed final click, and resume after handoff.
4. [x] Implement CLI, templates and review with tests first.
   Files: `tafnit.py`, `__init__.py`, shared tests.
   Support PDF picker, `--data`, `--items-csv`, `--dry-run`, `--resume`,
   `--config`, `--state-dir`, and `--open-final-confirmation`.
   Unknown PDFs stop after exporting review templates; input/profile changes
   block resume before desktop initialization. No automatic approval flag.
5. [x] Document setup, schema, supported mappings, privacy and recovery.
   Files: `README.md`, `FORMAT.md`, root README and relevant docs/ignore rules.
   Run all offline tests, both CLI invocation styles, example validation,
   whitespace checks and a focused review of the final handoff paths.
