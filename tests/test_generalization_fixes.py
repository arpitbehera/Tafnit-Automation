"""Regression coverage for fixes found during actual Rosh order entry."""
import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Generalization import configuration, desktop, quotation, tafnit, workflow
from RoshElectroptics import rosh_thorlabs_tafnit as legacy
from test_generalization import CONFIG, QUOTE, FakeDesktop, live_rows
from test_rosh_thorlabs_tafnit import QUOTE as ROSH_QUOTE


class QuotationFixTests(unittest.TestCase):
    def test_description_keeps_source_and_verifies_transport_safe_signs(self):
        data = copy.deepcopy(QUOTE)
        data["items"][0]["description"] = "Adapter ≥12 mm, ≤20 mm, Ø5 mm"
        q = quotation.parse_quotation(data)
        rows = live_rows()
        rows[0][9] = "Adapter >=12 mm, <=20 mm, dia. 5 mm"
        self.assertEqual(desktop.verify_rows(q, rows, configuration.parse_config(CONFIG)), 2)
        self.assertEqual(q.items[0].description, "Adapter ≥12 mm, ≤20 mm, Ø5 mm")
        rows[0][9] = "Adapter ?12 mm, ?20 mm, ?5 mm"
        with self.assertRaisesRegex(legacy.AutomationError, "description"):
            desktop.verify_rows(q, rows, configuration.parse_config(CONFIG))

    def test_rosh_uk_note_is_normalized_but_generic_suffixes_are_preserved(self):
        q = quotation.parse_known_pdf_text(ROSH_QUOTE.replace("1 DEMO-CUBE", "1 DEMO-CUBE (UK)"))
        self.assertEqual(q.items[0].part_number, "DEMO-CUBE")
        self.assertIn("DEMO-CUBE (UK)", q.notes)
        self.assertEqual(q.items[0].website, "https://www.thorlabs.com/item/DEMO-CUBE")
        q = quotation.parse_known_pdf_text(ROSH_QUOTE.replace("1 DEMO-CUBE", "1 DEMO-CUBE (LEFT)"))
        self.assertEqual(q.items[0].part_number, "DEMO-CUBE (LEFT)")
        data = copy.deepcopy(QUOTE)
        data["items"][0]["part_number"] = "EX-1 (UK)"
        self.assertEqual(quotation.parse_quotation(data).items[0].part_number, "EX-1 (UK)")

    def test_known_rosh_product_url_encodes_slash(self):
        q = quotation.parse_known_pdf_text(ROSH_QUOTE.replace("1 DEMO-CUBE", "1 DEMO-CUBE/M (DE WH)"))
        self.assertEqual(q.items[0].website, "https://www.thorlabs.com/item/DEMO-CUBE%2FM")

    def test_optional_websites_roundtrip_in_json_and_csv(self):
        data = copy.deepcopy(QUOTE)
        data["items"][0]["website"] = "https://vendor.example/items/EX-1"
        q = quotation.parse_quotation(data)
        self.assertEqual(q.items[0].website, data["items"][0]["website"])
        self.assertEqual(q.to_dict(), data)
        self.assertEqual(quotation.parse_quotation(QUOTE).to_dict(), QUOTE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quote.json"
            path.write_text(json.dumps(dict(data, items=[])))
            csv = Path(directory) / "items.csv"
            quotation.export_csv(q, csv)
            self.assertEqual(quotation.load_quotation(path, csv).to_dict(), data)

    def test_invalid_websites_stop_before_entry(self):
        for site in ("javascript:alert(1)", "vendor.example", "https://", "https://vendor.example/bad path", 123):
            with self.subTest(site=site), self.assertRaises(quotation.QuotationError):
                data = copy.deepcopy(QUOTE)
                data["items"][0]["website"] = site
                quotation.parse_quotation(data)


class DesktopFixTests(unittest.TestCase):
    def make_ui(self, *, existing_site="", catalog="", fallback="https://vendor.example"):
        ui = object.__new__(desktop.GeneralDesktop)
        ui.config = configuration.parse_config(CONFIG)
        ui.quote = quotation.parse_quotation(QUOTE)
        ui.supplier = SimpleNamespace(website=fallback)
        values = {"ln": "1", "Cat": "", "CatSpk": "", "WebSite": existing_site,
                  "DescLarge": "Catalog description"}
        saved = []
        ui.value = lambda field: values[field]
        def fill(field, value, **kwargs):
            values[field] = str(value)
            if field == "CatSpk": values["Cat"] = catalog
        ui.fill = fill
        ui.select = lambda field, value: values.update({field: value})
        ui.screenshot = lambda name: None
        def click(name):
            if name == "KSVLIN":
                saved.append(dict(values))
                values["ln"] = "2"
        ui.click = click
        return ui, values, saved

    def test_catalog_entry_preserves_reviewed_configuration_description(self):
        ui, _, saved = self.make_ui(catalog="1234")
        item = replace(ui.quote.items[0], description="Custom fiber, 4 meters, Ø3 mm tubing")
        with patch.object(desktop.time, "sleep"):
            ui.enter_item(item, 1)
        self.assertEqual(saved[0]["DescLarge"], "Custom fiber, 4 meters, dia. 3 mm tubing")

    def test_shared_catalog_part_cannot_hide_different_configurations(self):
        data = copy.deepcopy(QUOTE)
        data["items"][0]["description"] = "Custom fiber, 2 meters"
        data["items"][1].update(part_number="EX-1", description="Custom fiber, 4 meters")
        q = quotation.parse_quotation(data)
        rows = live_rows()
        for item, row in zip(q.items, rows):
            row[7], row[9], row[10] = "EX-1", item.tafnit_description, "1234"
        config = configuration.parse_config(CONFIG)
        self.assertEqual(desktop.verify_rows(q, rows, config), 2)
        rows[1][9] = rows[0][9]
        with self.assertRaisesRegex(legacy.AutomationError, "description"):
            desktop.verify_rows(q, rows, config)

    def test_entry_fills_safe_description_and_fallback_website_before_save(self):
        ui, values, saved = self.make_ui()
        item = replace(ui.quote.items[0], description="Adapter ≥12 mm, ≤20 mm, Ø5 mm")
        with patch.object(desktop.time, "sleep"):
            ui.enter_item(item, 1)
        self.assertEqual(saved[0]["DescLarge"], "Adapter >=12 mm, <=20 mm, dia. 5 mm")
        self.assertEqual(saved[0]["WebSite"], "https://vendor.example")
        self.assertEqual(saved[0]["Scm"], "10.01")

    def test_product_url_beats_supplier_fallback_and_catalog_link_is_preserved(self):
        data = copy.deepcopy(QUOTE)
        data["items"][0]["website"] = "https://vendor.example/product"
        item = quotation.parse_quotation(data).items[0]
        for catalog in ("", "1234"):
            for existing in ("", "https://catalog.example/resolved"):
                with self.subTest(catalog=catalog, existing=existing):
                    ui, _, saved = self.make_ui(catalog=catalog, existing_site=existing)
                    with patch.object(desktop.time, "sleep"):
                        ui.enter_item(item, 1)
                    self.assertEqual(saved[0]["WebSite"], existing if catalog and existing else "https://vendor.example/product")
                    self.assertEqual(saved[0]["DescLarge"], item.tafnit_description)

    def test_missing_website_stops_before_row_save(self):
        for stale in ("", "https://other.example/previous-item"):
            with self.subTest(stale=stale):
                ui, _, saved = self.make_ui(fallback="", existing_site=stale)
                with patch.object(desktop.time, "sleep"), self.assertRaisesRegex(legacy.AutomationError, "website"):
                    ui.enter_item(ui.quote.items[0], 1)
                self.assertEqual(saved, [])

    def test_unit_lookup_uses_case_sensitive_attribute_selector(self):
        ui, _, saved = self.make_ui(existing_site="https://vendor.example")
        ui.config = replace(ui.config, unit_field="Unit", units={"PCS": {"code": "7", "row_labels": ["pcs"]}})
        def element(selector):
            self.assertEqual(selector, '[id="Unit"]')
            return {"options": [{"value": "7", "text": "pcs"}]}
        ui.element = element
        with patch.object(desktop.time, "sleep"):
            ui.enter_item(ui.quote.items[0], 1)
        self.assertEqual(saved[0]["Unit"], "7")

    def test_inherited_save_handles_absent_blank_and_populated_archive_description(self):
        for description in (None, "", "Quote Q-42"):
            with self.subTest(description=description):
                ui = object.__new__(desktop.GeneralDesktop)
                actions = []
                ui.reader = SimpleNamespace(read=lambda expression: description)
                ui.value = lambda field: "1234" if field == "COM" else self.fail("Unexpected strict DESC read")
                ui.click = actions.append
                ui.fill = lambda field, value: actions.append((field, value))
                ui.click_selector = lambda selector: actions.append("close-archive")
                ui.screenshot = lambda name: None
                with patch.object(desktop.time, "sleep"):
                    self.assertEqual(ui.save(), "1234")
                self.assertEqual(actions[-1], "KSAVE")
                self.assertEqual("BOpenArchiveUtilWin" in actions, description == "")

    def test_inherited_fill_and_select_use_exact_case_ids(self):
        ui = object.__new__(desktop.GeneralDesktop)
        seen = []
        ui.element = lambda selector: seen.append(selector) or {
            "readonly": False, "maxlength": 100, "point": (1, 2), "options": [{"value": "007", "text": "Seven"}]}
        ui.p = SimpleNamespace(click=lambda *args: None, hotkey=lambda *args: None, press=lambda *args, **kwargs: None)
        ui.clipboard = SimpleNamespace(copy=lambda value: None)
        ui.value = lambda field: "007"
        with patch.object(desktop.time, "sleep"):
            ui.fill("SPK", "007")
            ui.select("Unit", "007")
        self.assertEqual(seen, ['[id="SPK"]', '[id="Unit"]'])


class WorkflowFixTests(unittest.TestCase):
    def test_full_page_save_corruption_stops_before_handoff(self):
        ui = FakeDesktop()
        original_save = ui.save
        def save():
            result = original_save()
            ui.rows[0][9] = "Corrupted after page save"
            return result
        ui.save = save
        with tempfile.TemporaryDirectory() as directory:
            state = legacy.Checkpoint(Path(directory) / "state.json", "hash", resume=False)
            with self.assertRaisesRegex(legacy.AutomationError, "description"):
                workflow.run_entry(ui, quotation.parse_quotation(QUOTE), Path("quote.pdf"), state,
                                   configuration.parse_config(CONFIG), open_final_confirmation=True)
            self.assertNotIn(("handoff",), ui.actions)
            self.assertNotEqual(state.data["stage"], "awaiting_user_confirmation")


class SupplierFixTests(unittest.TestCase):
    def test_supplier_prompt_accepts_validated_generic_website(self):
        answers = iter(["007", "Example Instruments Ltd", "", "https://vendor.example"])
        with contextlib.redirect_stdout(io.StringIO()):
            supplier = configuration.prompt_supplier("Example Instruments Ltd", ask=lambda _: next(answers))
        self.assertEqual(supplier.website, "https://vendor.example")
        self.assertEqual(supplier.to_dict()["website"], "https://vendor.example")

    def test_new_optional_fields_preserve_existing_checkpoint_fingerprint(self):
        old_supplier = {"code": "007", "name": "Example Instruments Ltd", "agent_code": ""}
        payload = {"quote": QUOTE, "config": CONFIG, "supplier": old_supplier}
        old_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        q = quotation.parse_quotation(QUOTE)
        config = configuration.parse_config(CONFIG)
        supplier = configuration.Supplier(**old_supplier)
        self.assertEqual(tafnit.fingerprint(q, config, supplier), old_hash)
        data = copy.deepcopy(QUOTE)
        data["items"][0]["website"] = "https://vendor.example/product"
        self.assertNotEqual(tafnit.fingerprint(quotation.parse_quotation(data), config, supplier), old_hash)
        self.assertNotEqual(tafnit.fingerprint(q, config, replace(supplier, website="https://vendor.example")), old_hash)


if __name__ == "__main__":
    unittest.main()
