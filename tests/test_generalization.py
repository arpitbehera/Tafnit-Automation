"""Synthetic tests; never import GUI drivers or operate a real requisition."""
import copy
import contextlib
import importlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from RoshElectroptics import rosh_thorlabs_tafnit as legacy


QUOTE = {
    "schema_version": 1, "vendor_name": "Example Instruments Ltd", "number": "Q-42",
    "date": "2030-01-02", "currency": "EUR", "currency_decimals": 2,
    "payment_terms": "30 days", "notes": "Freight included as a separate line",
    "net_total": "28.02", "tax_total": "5.60", "total": "33.62",
    "items": [
        {"part_number": "EX-1", "description": "Example sensor", "quantity": "2",
         "unit": "PCS", "unit_price": "10.01", "discount_percent": "0", "line_total": "20.02"},
        {"part_number": "", "description": "Freight", "quantity": "1",
         "unit": "PCS", "unit_price": "8", "discount_percent": "0", "line_total": "8.00"},
    ],
}
CONFIG = {
    "tafnit_host": "tafnit.example.edu",
    "header": {"MEHKAR": "001", "IZAM": "002", "MHLK": "003", "Building": "1",
               "Floor": "2", "Room": "3", "CBuilding": "1", "CFloor": "2", "CRoom": "3"},
    "budget_note": "Example funding", "request_type_code": "4", "purpose_code": "1",
    "currencies": {"EUR": {"code": "2", "row_labels": ["EUR", "Euro"],
                            "net_total_field": "ExampleNet", "tax_total_field": "ExampleTax",
                            "gross_total_field": "ExampleGross"}},
    "unit_field": "", "units": {"PCS": {"code": "", "row_labels": [""]}},
    "classification": {"category_code": "1", "subcategory_code": "7"},
    "customs": {"required": False, "description": "", "usage": ""},
}


def module(name):
    try:
        return importlib.import_module("Generalization." + name)
    except ModuleNotFoundError as exc:
        raise AssertionError("Generalized " + name + " component has not been implemented") from exc


class QuotationTests(unittest.TestCase):
    def test_known_rosh_parser_normalizes_only_warehouse_suffix_with_audit_note(self):
        from test_rosh_thorlabs_tafnit import HEADER
        source = HEADER + '''1 DEMO-B (DE WH)
Achromatic Fiber Collimator
DEU
1.00 PCS USD 100.01 10.00% 90.01 90.01
TOTAL USD 90.01'''
        q = module("quotation").parse_known_pdf_text(source)
        self.assertEqual(q.items[0].part_number, "DEMO-B")
        self.assertIn("DEMO-B (DE WH)", q.notes)

    def test_vendor_independent_amounts_and_date(self):
        q = module("quotation").parse_quotation(copy.deepcopy(QUOTE))
        self.assertEqual(q.vendor_name, "Example Instruments Ltd")
        self.assertEqual(q.currency, "EUR")
        self.assertEqual(q.tafnit_date, "02/01/2030")
        self.assertEqual(q.exact_total, Decimal("28.02"))
        self.assertEqual(q.items[1].part_number, "")

    def test_rejects_inconsistent_or_unrepresentable_quotes(self):
        m = module("quotation")
        bad_cases = [
            ("net_total", "28.03"), ("total", "33.63"), ("tax_total", "NaN"),
            ("currency", "$"), ("date", "01/02/2030"), ("schema_version", True),
            ("items", []), ("vendor_name", ""), ("currency_decimals", 5),
        ]
        for key, value in bad_cases:
            with self.subTest(key=key), self.assertRaises(m.QuotationError):
                data = copy.deepcopy(QUOTE)
                data[key] = value
                m.parse_quotation(data)

    def test_rejects_bad_item_math_and_precision(self):
        m = module("quotation")
        for key, value in [("quantity", "0"), ("unit_price", "-1"), ("unit_price", "10.0101"),
                           ("discount_percent", "101"), ("discount_percent", "1.001"),
                           ("line_total", "20.01"), ("unit", ""), ("quantity", "1,000"),
                           ("quantity", 2.0), ("description", "unsafe\x1b[2J")]:
            with self.subTest(key=key, value=value), self.assertRaises(m.QuotationError):
                data = copy.deepcopy(QUOTE)
                data["items"][0][key] = value
                m.parse_quotation(data)

    def test_discount_rounding_uses_original_price(self):
        m = module("quotation")
        data = copy.deepcopy(QUOTE)
        data["items"] = [dict(data["items"][0], quantity="5", discount_percent="10", line_total="45.05")]
        data.update(net_total="45.05", tax_total="0", total="45.05")
        q = m.parse_quotation(data)
        self.assertEqual(q.items[0].unit_price, Decimal("10.01"))
        self.assertEqual(q.exact_total, Decimal("45.045"))

    def test_unknown_keys_and_duplicate_json_fields_are_rejected(self):
        m = module("quotation")
        with self.assertRaises(m.QuotationError):
            m.parse_quotation(dict(QUOTE, shipping="10"))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "quote.json"
            path.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaisesRegex(m.QuotationError, "Duplicate"):
                m.load_quotation(path)

    def test_csv_import_preserves_decimal_strings_and_rejects_extra_cells(self):
        m = module("quotation")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "quote.json"
            path.write_text(json.dumps(dict(QUOTE, items=[])))
            csv = Path(d) / "items.csv"
            csv.write_text('part_number,description,quantity,unit,unit_price,discount_percent,line_total\n'
                           'EX-1,Example sensor,2,PCS,10.01,0,20.02\n'
                           ',Freight,1,PCS,8,0,8.00\n')
            self.assertEqual(m.load_quotation(path, csv).exact_total, Decimal("28.02"))
            csv.write_text(csv.read_text() + ',Extra,1,PCS,8,0,8.00,unexpected\n')
            with self.assertRaises(m.QuotationError):
                m.load_quotation(path, csv)


class ConfigurationTests(unittest.TestCase):
    def test_mapping_requires_matching_currency_units_and_tax_readback(self):
        m = module("configuration")
        q = module("quotation").parse_quotation(copy.deepcopy(QUOTE))
        config = m.parse_config(copy.deepcopy(CONFIG))
        m.validate_mapping(q, config)
        for mutate in [lambda d: d["currencies"].clear(),
                       lambda d: d["units"].clear(),
                       lambda d: d["currencies"]["EUR"].update(tax_total_field=""),
                       lambda d: d["currencies"]["EUR"].update(gross_total_field="")]:
            data = copy.deepcopy(CONFIG)
            mutate(data)
            with self.assertRaises(m.ConfigurationError):
                m.validate_mapping(q, m.parse_config(data))

    def test_blank_profile_and_unsafe_field_mappings_rejected(self):
        m = module("configuration")
        for key, value in [("tafnit_host", "https://wrong/path"), ("budget_note", ""),
                           ("header", {"SPK": "999"}), ("unit_field", "Coin"),
                           ("customs", {"required": "false", "description": "", "usage": ""})]:
            with self.subTest(key=key), self.assertRaises(m.ConfigurationError):
                m.parse_config(dict(copy.deepcopy(CONFIG), **{key: value}))

    def test_supplier_prompt_has_no_thorlabs_defaults(self):
        m = module("configuration")
        answers = iter(["007123", "EXAMPLE INSTRUMENTS LTD", "", ""])
        supplier = m.prompt_supplier("Example Instruments Ltd", ask=lambda _: next(answers))
        self.assertEqual(supplier.code, "007123")
        self.assertEqual(supplier.name, "EXAMPLE INSTRUMENTS LTD")
        self.assertEqual(supplier.agent_code, "")


def live_rows():
    return [["", "", "20.020", "10.010", "EUR", "0", "2", "", "", "Example sensor", "", "1"],
            ["", "", "8.000", "8.000", "EUR", "0", "1", "", "", "Freight", "", "2"]]


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.q = module("quotation").parse_quotation(copy.deepcopy(QUOTE))
        self.config = module("configuration").parse_config(copy.deepcopy(CONFIG))

    def test_rows_reject_wrong_currency_unit_identity_and_prices(self):
        m = module("desktop")
        self.assertEqual(m.verify_rows(self.q, live_rows(), self.config), 2)
        for index, value in [(4, "USD"), (8, "BOX"), (9, "Different sensor"), (3, "9.01"), (2, "20.00")]:
            rows = live_rows()
            rows[0][index] = value
            with self.subTest(index=index), self.assertRaises(legacy.AutomationError):
                m.verify_rows(self.q, rows, self.config)

    def test_catalog_item_requires_exact_part_and_unit(self):
        m = module("desktop")
        rows = live_rows()
        rows[0][7], rows[0][10] = "EX-1", "1001"
        self.assertEqual(m.verify_rows(self.q, rows, self.config), 2)
        rows[0][7] = "EX-2"
        with self.assertRaises(legacy.AutomationError):
            m.verify_rows(self.q, rows, self.config)

    def test_header_checks_resolved_supplier_and_agent(self):
        m = module("desktop")
        ui = object.__new__(m.GeneralDesktop)
        ui.config = self.config
        ui.supplier = module("configuration").Supplier("007", "EXAMPLE INSTRUMENTS LTD", "")
        values = dict(CONFIG["header"], SUGD="4", MHTD="1", KM="2", SEIF="",
                      SPK="007", HSPK="Example Instruments Ltd", SOCHEN="", REMARKINS="Example funding")
        class Reader:
            def read(self, expression): return dict(values)
        ui.reader = Reader()
        ui.verify_header(self.q)
        for field in ("HSPK", "SPK", "SOCHEN", "KM"):
            previous = values[field]
            values[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(legacy.AutomationError):
                ui.verify_header(self.q)
            values[field] = previous

    def test_no_part_number_skips_catalog_lookup_and_uses_configured_classification(self):
        m = module("desktop")
        ui = object.__new__(m.GeneralDesktop)
        ui.config = self.config
        ui.quote = self.q
        ui.supplier = module("configuration").Supplier("007", "Example Instruments Ltd", "", "https://vendor.example")
        values = {"ln": "2", "Cat": "", "CatSpk": "", "WebSite": "https://vendor.example"}
        actions = []
        ui.value = lambda field: values[field]
        ui.fill = lambda field, value, **kwargs: actions.append(("fill", field, str(value)))
        ui.select = lambda field, value: actions.append(("select", field, value))
        ui.screenshot = lambda _: None
        def click(name):
            actions.append(("click", name))
            if name == "KSVLIN": values["ln"] = "3"
        ui.click = click
        with patch.object(m.time, "sleep"):
            ui.enter_item(self.q.items[1], 2)
        self.assertIn(("fill", "Coin", "2"), actions)
        self.assertIn(("fill", "DescLarge", "Freight"), actions)
        self.assertNotIn(("fill", "CatSpk", ""), actions)
        self.assertIn(("select", "KitlugFLD0B", "7"), actions)

    def test_resume_after_upload_closes_the_remaining_archive_dialog(self):
        m = module("desktop")
        ui = object.__new__(m.GeneralDesktop)
        actions = []
        ui.click = lambda name: actions.append(name)
        ui.attachment_rows = lambda: ["Quote Q-42"]
        class Reader:
            def read(self, expression): return True
        ui.reader = Reader()
        ui.click_selector = lambda selector: actions.append(selector)
        ui.attach_quote(self.q, Path("unused.pdf"))
        self.assertIn('#ArchiveUtilWin img[onclick*="CloseArchiveUtilWin"]', actions)


class FakeDesktop:
    """Real workflow/verification over deterministic table and save boundaries."""
    def __init__(self, rows=None):
        self.rows = live_rows() if rows is None else rows
        self.actions = []
        self.values = {"COM": "", "STTS": "0", "ExampleNet": "28.020", "ExampleTax": "5.60", "ExampleGross": "33.62"}
        self.attachments = ["Quote Q-42"]
    def value(self, field):
        self.actions.append(("value", field))
        return self.values[field]
    def prepare(self, q, pdf): self.actions.append(("prepare",))
    def verify_header(self, q): self.actions.append(("header",))
    def item_rows(self):
        self.actions.append(("rows",))
        return self.rows
    def begin_items(self, line): self.actions.append(("begin", line))
    def enter_item(self, item, line):
        self.actions.append(("enter", line))
        self.rows.append(live_rows()[line - 1])
    def save(self):
        self.actions.append(("save",))
        self.values["COM"] = "1234"
        return "1234"
    def ensure_customs(self, state): self.actions.append(("customs",))
    def click(self, name): self.actions.append(("click", name))
    def attachment_rows(self): return self.attachments
    def open_final_confirmation(self): self.actions.append(("handoff",))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.q = module("quotation").parse_quotation(copy.deepcopy(QUOTE))
        self.config = module("configuration").parse_config(copy.deepcopy(CONFIG))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = legacy.Checkpoint(Path(self.temp.name) / "state.json", "pdf-hash", resume=False)

    def run_entry(self, ui, **kwargs):
        return module("workflow").run_entry(ui, self.q, Path("quote.pdf"), self.state, self.config, **kwargs)

    def test_default_run_saves_draft_without_submission(self):
        ui = FakeDesktop()
        self.run_entry(ui)
        self.assertEqual(self.state.data["stage"], "draft_ready")
        self.assertNotIn(("handoff",), ui.actions)
        self.assertNotIn(("customs",), ui.actions)

    def test_final_handoff_is_last_action_and_blocks_all_resume_input(self):
        ui = FakeDesktop()
        self.run_entry(ui, open_final_confirmation=True)
        self.assertEqual(ui.actions[-1], ("handoff",))
        self.assertEqual(self.state.data["stage"], "awaiting_user_confirmation")
        before = list(ui.actions)
        with self.assertRaises(legacy.AutomationError):
            self.run_entry(ui, open_final_confirmation=True)
        self.assertEqual(ui.actions, before)

    def test_failed_handoff_cannot_be_retried(self):
        ui = FakeDesktop()
        def fail(): raise legacy.AutomationError("Lost window")
        ui.open_final_confirmation = fail
        with self.assertRaisesRegex(legacy.AutomationError, "Lost window"):
            self.run_entry(ui, open_final_confirmation=True)
        saved = json.loads(self.state.path.read_text())
        self.assertEqual(saved["stage"], "awaiting_user_confirmation")

    def test_crash_after_row_save_uses_live_rows_on_resume(self):
        self.state.update(stage="items", rows=0, pending_line=1)
        ui = FakeDesktop(rows=live_rows()[:1])
        self.run_entry(ui)
        self.assertEqual([a for a in ui.actions if a[0] == "enter"], [("enter", 2)])

    def test_wrong_tax_or_extra_attachment_never_opens_confirmation(self):
        for change in ("tax", "attachment"):
            with self.subTest(change=change):
                ui = FakeDesktop()
                self.state.update(stage="items", request="")
                if change == "tax": ui.values["ExampleTax"] = "5.00"
                else: ui.attachments.append("Unexpected attachment")
                with self.assertRaises(legacy.AutomationError):
                    self.run_entry(ui, open_final_confirmation=True)
                self.assertNotIn(("handoff",), ui.actions)

    def test_non_new_request_or_wrong_saved_request_is_never_edited(self):
        for values in ({"STTS": "1"}, {"COM": "123"}):
            ui = FakeDesktop()
            ui.values.update(values)
            with self.assertRaises(legacy.AutomationError):
                self.run_entry(ui)
            self.assertFalse(any(a[0] in ("prepare", "save", "enter") for a in ui.actions))

    def test_crash_after_save_requires_full_rows_and_matching_attachment_before_adoption(self):
        for partial in (True, False):
            self.state.update(stage="saving", rows=2, request="")
            ui = FakeDesktop(rows=live_rows()[:1] if partial else live_rows())
            ui.values["COM"] = "9999"
            ui.attachments = ["Quote OTHER"]
            with self.subTest(partial=partial), self.assertRaises(legacy.AutomationError):
                self.run_entry(ui)
            self.assertFalse(any(a[0] in ("save", "enter") for a in ui.actions))

    def test_resume_rejects_deleted_rows_before_reentering_them(self):
        self.state.update(stage="items", rows=2)
        ui = FakeDesktop(rows=live_rows()[:1])
        with self.assertRaises(legacy.AutomationError):
            self.run_entry(ui)
        self.assertFalse(any(a[0] in ("save", "enter") for a in ui.actions))

    def test_unsaved_resume_checks_attachment_before_adding_missing_rows(self):
        self.state.update(stage="items", rows=1)
        ui = FakeDesktop(rows=live_rows()[:1])
        ui.attachments = ["Quote OTHER"]
        with self.assertRaises(legacy.AutomationError):
            self.run_entry(ui)
        self.assertFalse(any(a[0] in ("save", "enter") for a in ui.actions))

    def test_unmapped_tax_and_gross_mark_draft_unverified_and_block_handoff_before_ui(self):
        data = copy.deepcopy(QUOTE)
        data.update(tax_total="0", total="28.02")
        self.q = module("quotation").parse_quotation(data)
        profile = copy.deepcopy(CONFIG)
        profile["currencies"]["EUR"].update(tax_total_field="", gross_total_field="")
        self.config = module("configuration").parse_config(profile)
        ui = FakeDesktop()
        self.run_entry(ui)
        self.assertEqual(self.state.data["unverified_totals"], ["tax", "gross"])
        ui.actions.clear()
        with self.assertRaises(module("configuration").ConfigurationError):
            self.run_entry(ui, open_final_confirmation=True)
        self.assertEqual(ui.actions, [])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "quote.local.json"
        self.data.write_text(json.dumps(QUOTE))
        self.config = self.root / "config.local.json"
        self.config.write_text(json.dumps(CONFIG))
        self.pdf = self.root / "quote.pdf"
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        writer.write(str(self.pdf))
        self.artifacts = self.root / "run-tafnit"

    def invoke(self, args, answers=()):
        m = module("tafnit")
        prompts = []
        iterator = iter(answers)
        def ask(question):
            prompts.append(question)
            return next(iterator)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = m.main(args, ask=ask)
        return code, prompts

    def test_dry_run_needs_no_config_pdf_or_supplier_input(self):
        m = module("tafnit")
        with patch.object(m, "GeneralDesktop", side_effect=AssertionError("Desktop must stay untouched")):
            code, prompts = self.invoke(["--data", str(self.data), "--dry-run", "--state-dir", str(self.artifacts)])
        self.assertEqual(code, 0)
        self.assertEqual(prompts, [])
        self.assertTrue((self.artifacts / "quotation.review.local.json").exists())
        self.assertFalse((self.artifacts / "state.json").exists())

    def test_bare_dry_run_is_usage_error_without_file_picker(self):
        m = module("tafnit")
        with patch.object(m, "pick_pdf", side_effect=AssertionError("No GUI in dry-run")):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                m.main(["--dry-run"])
        self.assertEqual(caught.exception.code, 2)

    def test_review_export_never_overwrites_json_or_csv_inputs(self):
        self.artifacts.mkdir()
        colliding_data = self.artifacts / "quotation.review.local.json"
        colliding_csv = self.artifacts / "items.review.csv"
        colliding_data.write_text(json.dumps(dict(QUOTE, items=[])))
        colliding_csv.write_text('part_number,description,quantity,unit,unit_price,discount_percent,line_total\n'
                                 'EX-1,Example sensor,2,PCS,10.01,0,20.02\n,Freight,1,PCS,8,0,8.00\n')
        before = (colliding_data.read_bytes(), colliding_csv.read_bytes())
        code, _ = self.invoke(["--data", str(colliding_data), "--items-csv", str(colliding_csv),
                               "--dry-run", "--state-dir", str(self.artifacts)])
        self.assertEqual(code, 1)
        self.assertEqual((colliding_data.read_bytes(), colliding_csv.read_bytes()), before)

    def test_unknown_or_scanned_pdf_writes_templates_and_stops(self):
        m = module("tafnit")
        with patch.object(m, "GeneralDesktop", side_effect=AssertionError("Desktop must stay untouched")):
            code, prompts = self.invoke([str(self.pdf), "--state-dir", str(self.artifacts)])
        self.assertEqual(code, 2)
        self.assertEqual(prompts, [])
        template = self.artifacts / "quotation.template.local.json"
        self.assertTrue(template.exists())
        template.write_text('operator edits')
        self.invoke([str(self.pdf), "--state-dir", str(self.artifacts)])
        self.assertEqual(template.read_text(), 'operator edits')

    def test_declining_review_does_not_create_checkpoint_or_operate_desktop(self):
        m = module("tafnit")
        args = [str(self.pdf), "--data", str(self.data), "--config", str(self.config), "--state-dir", str(self.artifacts)]
        with patch.object(m, "GeneralDesktop", side_effect=AssertionError("Desktop must stay untouched")):
            code, prompts = self.invoke(args, ["007", "Example Instruments Ltd", "", "", "no"])
        self.assertEqual(code, 0)
        self.assertEqual(len(prompts), 5)
        self.assertFalse((self.artifacts / "state.json").exists())

    def test_live_vendor_prompt_then_resume_rejects_changed_input_before_gui(self):
        m = module("tafnit")
        args = [str(self.pdf), "--data", str(self.data), "--config", str(self.config), "--state-dir", str(self.artifacts)]
        ui = FakeDesktop()
        with patch.object(m, "GeneralDesktop", return_value=ui), patch.object(m.time, "sleep"):
            code, prompts = self.invoke(args, ["007", "Example Instruments Ltd", "", "https://vendor.example", "ENTER"])
        self.assertEqual(code, 0)
        self.assertEqual(len(prompts), 5)
        self.assertNotIn(("handoff",), ui.actions)
        changed = copy.deepcopy(QUOTE)
        changed["items"][0]["description"] = "Different product at same price"
        self.data.write_text(json.dumps(changed))
        with patch.object(m, "GeneralDesktop", side_effect=AssertionError("Changed input must stop before desktop")):
            code, _ = self.invoke(args + ["--resume"])
        self.assertEqual(code, 1)

    def test_handoff_resume_is_blocked_before_prompts_and_gui(self):
        m = module("tafnit")
        args = [str(self.pdf), "--data", str(self.data), "--config", str(self.config), "--state-dir", str(self.artifacts)]
        answers = iter(["007", "Example Instruments Ltd", "", "", "ENTER"])
        with patch.object(m, "GeneralDesktop", return_value=FakeDesktop()), patch.object(m.time, "sleep"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = m.main(args + ["--open-final-confirmation"],
                              ask=lambda _: next(answers))
        self.assertEqual(code, 0)
        self.assertIn("confirmation or validation message", output.getvalue())
        with patch.object(m, "GeneralDesktop", side_effect=AssertionError("Handoff must stop before desktop")):
            code, prompts = self.invoke(args + ["--resume"])
        self.assertEqual(code, 1)
        self.assertEqual(prompts, [])

    def test_resume_accepts_pre_website_checkpoint_without_reprompting_supplier(self):
        import hashlib
        old_supplier = {"code": "007", "name": "Example Instruments Ltd", "agent_code": ""}
        payload = {"quote": QUOTE, "config": CONFIG, "supplier": old_supplier}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.artifacts.mkdir()
        (self.artifacts / "state.json").write_text(json.dumps({
            "workflow": "generalization-v1", "stage": "items", "rows": 0, "request": "",
            "pdf_sha256": hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
            "input_sha256": fingerprint, "supplier": old_supplier,
        }))
        m = module("tafnit")
        args = [str(self.pdf), "--data", str(self.data), "--config", str(self.config),
                "--state-dir", str(self.artifacts), "--resume"]
        with patch.object(m, "GeneralDesktop", return_value=FakeDesktop()), patch.object(m.time, "sleep"):
            code, prompts = self.invoke(args, ["ENTER"])
        self.assertEqual(code, 0)
        self.assertEqual(len(prompts), 1)

    def test_help_supports_direct_script_from_another_directory(self):
        module("tafnit")
        entry = Path(__file__).resolve().parents[1] / "Generalization" / "tafnit.py"
        result = subprocess.run([sys.executable, str(entry), "--help"], cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dry-run", result.stdout)


if __name__ == "__main__":
    unittest.main()
