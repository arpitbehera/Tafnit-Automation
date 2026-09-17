"""Prepare a Tafnit draft from a locally reviewed quotation for any vendor.

Unknown PDF layouts need reviewed --data JSON, optionally with --items-csv.
Supplier details are prompted for live entry. Final approval is always manual.
See Generalization/README.md for setup, supported mappings and recovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

# Support both an absolute script path and `python -m Generalization.tafnit`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from RoshElectroptics.rosh_thorlabs_tafnit import AutomationError, Checkpoint
from Generalization.configuration import ConfigurationError, Supplier, load_config, prompt_supplier, unverified_totals, validate_mapping
from Generalization.desktop import GeneralDesktop
from Generalization.quotation import (
    Quotation, QuotationError, export_csv, load_quotation, parse_known_pdf_text,
    read_json, read_pdf, write_templates,
)
from Generalization.workflow import STAGES, run_entry


def write_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def fingerprint(quote: Quotation, config, supplier: Supplier) -> str:
    payload = {"quote": quote.to_dict(), "config": asdict(config), "supplier": supplier.to_dict()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def protect_inputs(directory: Path, inputs: list[Path | None]) -> None:
    """Do not let generated review/checkpoint files overwrite any source input."""
    names = ("quotation.review.local.json", "quotation.review.local.json.tmp",
             "items.review.csv", "state.json", "state.tmp")
    for source in (path for path in inputs if path is not None):
        for name in names:
            output = directory / name
            same_file = source.exists() and output.exists() and source.samefile(output)
            if source.resolve() == output.resolve() or same_file:
                raise QuotationError(f"Input {source} collides with generated output {output}. Copy the input elsewhere or choose another --state-dir.")


def show_review(quote: Quotation) -> None:
    print(f"\nQuotation {quote.number} | {quote.vendor_name} | {quote.date} | {quote.currency}")
    for line, item in enumerate(quote.items, 1):
        print(f"{line}. {item.part_number or '(no part number)'} — {item.description}")
        print(f"   {item.quantity} {item.unit} × {item.unit_price}; discount {item.discount_percent}%; amount {item.line_total}")
        if item.tafnit_description != item.description:
            print(f"   Tafnit description: {item.tafnit_description}")
        if item.website:
            print(f"   Product website: {item.website}")
    print(f"Net: {quote.net_total}; tax: {quote.tax_total}; total: {quote.total} {quote.currency}")
    print(f"Tafnit net from entered prices: {quote.exact_total}")
    print(f"Payment terms: {quote.payment_terms or '(not specified)'}; notes: {quote.notes or '(none)'}")


def pick_pdf() -> Path | None:
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()
    try:
        chosen = filedialog.askopenfilename(title="Select vendor quotation", filetypes=[("PDF quotations", "*.pdf")])
    finally:
        root.destroy()
    return Path(chosen) if chosen else None


def main(argv: list[str] | None = None, *, ask: Callable[[str], str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path, nargs="?", help="quotation PDF; omitted opens a picker for live entry")
    parser.add_argument("--data", type=Path, help="reviewed quotation JSON, independent of vendor/PDF layout")
    parser.add_argument("--items-csv", type=Path, help="reviewed item CSV; requires --data with items: []")
    parser.add_argument("--dry-run", action="store_true", help="validate/export locally without desktop access or vendor prompts")
    parser.add_argument("--config", type=Path, help="local Tafnit profile; default: config.local.json beside this script")
    parser.add_argument("--state-dir", type=Path, help="local review/checkpoint/screenshot directory")
    parser.add_argument("--resume", action="store_true", help="resume the same PDF, reviewed data, supplier and profile")
    parser.add_argument("--open-final-confirmation", action="store_true", help="after draft verification, open the final dialog and stop; never approve it")
    args = parser.parse_args(argv)
    ask = input if ask is None else ask
    if args.items_csv and not args.data:
        parser.error("--items-csv requires --data")
    if args.dry_run and (args.resume or args.open_final_confirmation):
        parser.error("--dry-run cannot be combined with --resume or --open-final-confirmation")
    if args.dry_run and not (args.pdf or args.data):
        parser.error("--dry-run requires an explicit PDF or --data path; it never opens a file picker")
    try:
        pdf = args.pdf
        if pdf is None and not (args.dry_run and args.data):
            pdf = pick_pdf()
            if pdf is None:
                print("Cancelled.")
                return 0
        if pdf is not None:
            pdf = pdf.resolve(strict=True)
            if pdf.suffix.lower() != ".pdf" or not pdf.read_bytes().startswith(b"%PDF-"):
                raise QuotationError("Provide a PDF quotation for the attachment.")
        source_path = pdf or args.data.resolve(strict=True)
        directory = args.state_dir or source_path.parent / (source_path.stem + "-general-tafnit")
        config_path = args.config or Path(__file__).with_name("config.local.json")
        protect_inputs(directory, [pdf, args.data, args.items_csv, config_path])
        if args.data:
            quote = load_quotation(args.data, args.items_csv)
        else:
            source = read_pdf(pdf)
            try:
                quote = parse_known_pdf_text(source)
            except QuotationError as exc:
                write_templates(directory, source)
                print(f"{exc}\nNo Tafnit actions taken. Review templates in {directory}.")
                print("Fill quotation.template.local.json and its items, or use --items-csv items.template.csv.")
                print("Then rerun with --data <reviewed JSON> --dry-run. See Generalization/FORMAT.md.")
                return 2
        # PDF-only validation is useful without any institutional configuration.
        config = load_config(config_path) if args.config or not args.dry_run else None
        if config is not None:
            validate_mapping(quote, config, require_all_totals=args.open_final_confirmation)
        if args.dry_run:
            show_review(quote)
            directory.mkdir(parents=True, exist_ok=True)
            write_json(directory / "quotation.review.local.json", quote.to_dict())
            export_csv(quote, directory / "items.review.csv")
            print(f"Validated locally. Review files: {directory}. No desktop actions performed.")
            if config is None:
                print("Tafnit mappings were not checked; add --config to validate them too.")
            return 0

        pdf_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
        state_path = directory / "state.json"
        state = None
        if state_path.exists():
            if not args.resume:
                raise AutomationError("A checkpoint exists. Inspect the existing request and use --resume.")
            snapshot = read_json(state_path)
            if not isinstance(snapshot, dict) or snapshot.get("workflow") != "generalization-v1":
                raise AutomationError("This is not a generalized-workflow checkpoint.")
            if snapshot.get("stage") not in STAGES:
                raise AutomationError("Unrecognized checkpoint stage.")
            if snapshot["stage"] == "awaiting_user_confirmation":
                raise AutomationError("Final confirmation was already requested. Inspect Tafnit's confirmation or validation message; finish manually.")
            state = Checkpoint(state_path, pdf_hash, resume=True)
            vendor = snapshot.get("supplier")
            if not isinstance(vendor, dict) or set(vendor) not in ({"code", "name", "agent_code"}, {"code", "name", "agent_code", "website"}):
                raise AutomationError("Missing supplier details in checkpoint.")
            supplier = Supplier(**vendor)
            if state.data.get("input_sha256") != fingerprint(quote, config, supplier):
                raise AutomationError("Reviewed quotation, supplier or configuration changed; resume is blocked.")
        elif args.resume:
            raise AutomationError("Cannot resume: no checkpoint exists for this quotation.")
        else:
            supplier = prompt_supplier(quote.vendor_name, ask=ask)

        show_review(quote)
        print(f"\nTafnit supplier: {supplier.code} — {supplier.name}; agent: {supplier.agent_code or '(none)'}")
        print(f"Website fallback: {supplier.website or '(none; each item needs an item/catalog website)'}")
        print(f"Funding note: {config.budget_note}")
        print(f"Request type: {config.request_type_code}; purpose: {config.purpose_code}; classification: {config.classification}")
        print(f"Customs declaration: {'required' if config.customs['required'] else 'not requested'}")
        missing_totals = unverified_totals(quote, config)
        if missing_totals:
            print("UNVERIFIED in Tafnit: " + ", ".join(missing_totals) + " totals. Check them manually on the saved draft.")
        if config.customs["required"]:
            print(f"Description: {config.customs['description']}\nUse: {config.customs['usage']}")
        endpoint = "request final confirmation; Tafnit may display a validation message" if args.open_final_confirmation else "leave a saved draft for your review"
        print(f"The script will {endpoint}.")
        if ask("Compare every item and total with the PDF and verify the supplier. Type ENTER to start data entry: ").strip() != "ENTER":
            print("Cancelled before desktop entry.")
            return 0
        directory.mkdir(parents=True, exist_ok=True)
        if state is None:
            state = Checkpoint(state_path, pdf_hash, resume=False)
            state.update(workflow="generalization-v1", supplier=supplier.to_dict(),
                         input_sha256=fingerprint(quote, config, supplier))
        write_json(directory / "quotation.review.local.json", quote.to_dict())
        export_csv(quote, directory / "items.review.csv")
        print("Starting in 5 seconds. Leave mouse/keyboard alone; a screen corner or Ctrl+C stops automation.")
        time.sleep(5)
        ui = GeneralDesktop(directory, config, supplier, quote)
        run_entry(ui, quote, pdf, state, config, open_final_confirmation=args.open_final_confirmation)
        print("STOPPED after requesting final confirmation. Inspect Tafnit's confirmation or validation message; no final approval was clicked." if args.open_final_confirmation
              else f"Saved draft {state.data['request']}. Review and complete it manually in Tafnit.")
        if missing_totals:
            print("UNVERIFIED totals requiring manual review: " + ", ".join(missing_totals))
        return 0
    except (QuotationError, ConfigurationError, AutomationError, OSError, ValueError, EOFError, KeyboardInterrupt) as exc:
        print(f"Stopped: {exc or 'cancelled'}. Inspect any existing Tafnit draft before resuming.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
