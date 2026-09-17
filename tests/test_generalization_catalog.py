"""Synthetic regressions for the catalog and total mappings observed in Tafnit."""
import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Generalization import configuration, desktop, quotation, workflow
from RoshElectroptics import rosh_thorlabs_tafnit as legacy
from test_generalization import CONFIG, QUOTE, FakeDesktop, live_rows


def catalog_rows():
    rows = live_rows()
    rows[0][7], rows[0][9], rows[0][10] = "EX-1", "Catalog sensor", "1001"
    return rows


def catalog_details():
    return {"ln": "1", "Cat": "1001", "CatSpk": "EX-1", "Lbb3": "EX-1",
            "DescLarge": "Catalog sensor",
            "Remarks": "Quote Q-42, line 1: EX-1 - Example sensor"}


class CatalogEntryTests(unittest.TestCase):
    def make_ui(self, *, readonly=True, description="Catalog sensor", manufacturer="EX-1",
                remarks_writable=True):
        ui = object.__new__(desktop.GeneralDesktop)
        ui.config = configuration.parse_config(CONFIG)
        ui.quote = quotation.parse_quotation(QUOTE)
        ui.supplier = configuration.Supplier("007", "Example Instruments Ltd", "", "https://vendor.example")
        values = {"ln": "1", "Cat": "", "CatSpk": "", "Lbb3": "",
                  "DescLarge": "", "Remarks": "", "WebSite": ""}
        saved = []
        ui.value = lambda field: values[field]
        ui.element = lambda selector: {"readonly": readonly, "value": values["DescLarge"]}

        def fill(field, value, **kwargs):
            if (field == "DescLarge" and readonly) or (field == "Remarks" and not remarks_writable):
                raise legacy.AutomationError(f"Field {field} is read-only.")
            values[field] = str(value)
            if field == "CatSpk":
                values.update(Cat="1001", Lbb3=manufacturer, DescLarge=description)

        def click(name):
            if name == "KSVLIN":
                saved.append(dict(values))
                values["ln"] = "2"

        ui.fill, ui.click = fill, click
        ui.screenshot = lambda name: None
        return ui, saved

    def test_locked_catalog_description_keeps_quote_configuration_in_remarks(self):
        ui, saved = self.make_ui()
        item = replace(ui.quote.items[0], description="Sensor, 4 meters, Ø3 mm tubing")
        with patch.object(desktop.time, "sleep"):
            ui.enter_item(item, 1)
        self.assertEqual(saved[0]["DescLarge"], "Catalog sensor")
        self.assertEqual(saved[0]["Remarks"], "Quote Q-42, line 1: EX-1 - Sensor, 4 meters, dia. 3 mm tubing")
        self.assertEqual(saved[0]["Quan"], "2")
        self.assertEqual(saved[0]["Scm"], "10.01")

    def test_identical_locked_description_does_not_need_a_write(self):
        ui, saved = self.make_ui(description="Example sensor")
        with patch.object(desktop.time, "sleep"):
            ui.enter_item(ui.quote.items[0], 1)
        self.assertEqual(saved[0]["DescLarge"], "Example sensor")

    def test_mismatched_manufacturer_stops_before_saving_even_with_editable_description(self):
        ui, saved = self.make_ui(readonly=False, manufacturer="EX-OTHER")
        with patch.object(desktop.time, "sleep"), self.assertRaisesRegex(legacy.AutomationError, "part"):
            ui.enter_item(ui.quote.items[0], 1)
        self.assertEqual(saved, [])

    def test_unwritable_quote_remarks_stop_before_row_save(self):
        ui, saved = self.make_ui(remarks_writable=False)
        with patch.object(desktop.time, "sleep"), self.assertRaisesRegex(legacy.AutomationError, "Remarks"):
            ui.enter_item(ui.quote.items[0], 1)
        self.assertEqual(saved, [])


class CatalogReadbackTests(unittest.TestCase):
    def setUp(self):
        self.q = quotation.parse_quotation(QUOTE)
        self.config = configuration.parse_config(CONFIG)

    def verify(self, details, rows=None):
        return desktop.verify_rows(self.q, catalog_rows() if rows is None else rows, self.config,
                                   read_catalog_details=lambda line: details)

    def test_catalog_description_difference_requires_persisted_quote_remarks(self):
        self.assertEqual(self.verify(catalog_details()), 2)
        with self.assertRaisesRegex(legacy.AutomationError, "description"):
            desktop.verify_rows(self.q, catalog_rows(), self.config)

    def test_wrong_row_part_catalog_description_or_remarks_are_rejected(self):
        for field, value in [("ln", "2"), ("Cat", "9999"), ("CatSpk", "EX-2"),
                             ("Lbb3", "EX-2"), ("DescLarge", "Other catalog item"),
                             ("Remarks", ""), ("Remarks", "Quote Q-42, line 1: EX-1 - Different sensor"),
                             ("Remarks", "Quote Q-42, line 1: EX-1 - Example sensor EXTRA")]:
            with self.subTest(field=field, value=value), self.assertRaises(legacy.AutomationError):
                self.verify(dict(catalog_details(), **{field: value}))

    def test_remarks_cannot_mask_an_uncatalogued_description_mismatch(self):
        rows = catalog_rows()
        rows[0][10] = ""
        with self.assertRaisesRegex(legacy.AutomationError, "description"):
            self.verify(catalog_details(), rows)

    def test_shared_sku_configurations_need_their_own_saved_remarks(self):
        items = (replace(self.q.items[0], description="Sensor, 2 meters"),
                 replace(self.q.items[1], part_number="EX-1", description="Sensor, 4 meters"))
        q = replace(self.q, items=items)
        rows = live_rows()
        for row in rows:
            row[7], row[9], row[10] = "EX-1", "Catalog sensor", "1001"
        details = {1: dict(catalog_details(), Remarks="Quote Q-42, line 1: EX-1 - Sensor, 2 meters"),
                   2: dict(catalog_details(), ln="2", Remarks="Quote Q-42, line 2: EX-1 - Sensor, 4 meters")}
        self.assertEqual(desktop.verify_rows(q, rows, self.config, read_catalog_details=details.__getitem__), 2)
        details[2]["Remarks"] = details[1]["Remarks"]
        with self.assertRaises(legacy.AutomationError):
            desktop.verify_rows(q, rows, self.config, read_catalog_details=details.__getitem__)

    def test_detail_reader_opens_exact_saved_row_without_saving_it(self):
        ui = object.__new__(desktop.GeneralDesktop)
        actions = []
        ui.click = lambda name: actions.append(name)
        ui.click_selector = lambda selector: actions.append(selector)
        ui.reader = SimpleNamespace(read=lambda expression: catalog_details())
        self.assertEqual(ui.read_item_details(1), catalog_details())
        self.assertIn('tr[key="1"] [id="wbglngrid"]', actions)
        self.assertNotIn("KSVLIN", actions)
        self.assertNotIn("KSAVE", actions)


class CatalogWorkflowTests(unittest.TestCase):
    def run_entry(self, ui, state):
        workflow.run_entry(ui, quotation.parse_quotation(QUOTE), Path("quote.pdf"), state,
                           configuration.parse_config(CONFIG), open_final_confirmation=True)

    def test_crash_after_catalog_row_save_resumes_without_duplicate_entry(self):
        ui = FakeDesktop(rows=catalog_rows()[:1])
        ui.read_item_details = lambda line: catalog_details()
        with tempfile.TemporaryDirectory() as directory:
            state = legacy.Checkpoint(Path(directory) / "state.json", "hash", resume=False)
            state.update(stage="items", rows=0, pending_line=1)
            self.run_entry(ui, state)
            self.assertEqual([action for action in ui.actions if action[0] == "enter"], [("enter", 2)])
            self.assertEqual(state.data["stage"], "awaiting_user_confirmation")
            self.assertEqual(ui.actions[-1], ("handoff",))

    def test_quote_remarks_lost_on_page_save_block_handoff(self):
        ui = FakeDesktop(rows=catalog_rows())
        details = catalog_details()
        ui.read_item_details = lambda line: dict(details)
        original_save = ui.save

        def save():
            result = original_save()
            details["Remarks"] = ""
            return result

        ui.save = save
        with tempfile.TemporaryDirectory() as directory:
            state = legacy.Checkpoint(Path(directory) / "state.json", "hash", resume=False)
            with self.assertRaises(legacy.AutomationError):
                self.run_entry(ui, state)
            self.assertIn(("save",), ui.actions)
            self.assertNotIn(("handoff",), ui.actions)


class ObservedProfileTests(unittest.TestCase):
    def setUp(self):
        example = json.loads((Path(__file__).resolve().parents[1] / "Generalization/config.example.json").read_text(encoding="utf-8"))
        data = copy.deepcopy(CONFIG)
        data.update(currencies=example["currencies"], units=example["units"])
        self.config = configuration.parse_config(data)
        self.q = quotation.parse_quotation(dict(QUOTE, currency="USD"))

    def test_profile_accepts_observed_usd_and_each_labels_but_rejects_other_units(self):
        rows = live_rows()
        for row in rows:
            row[4] = "בהרא $"
        rows[0][7], rows[0][8], rows[0][10] = "EX-1", "EACH", "1001"
        self.assertEqual(desktop.verify_rows(self.q, rows, self.config), 2)
        rows[0][8] = "BOX"
        with self.assertRaisesRegex(legacy.AutomationError, "unit"):
            desktop.verify_rows(self.q, rows, self.config)

    def test_profile_reads_net_tax_and_gross_from_distinct_observed_fields(self):
        ui = FakeDesktop()
        ui.values.update(BrutoaDollar="28.020", MamDollar="5.60", NetoDollar="33.620")
        configuration.validate_mapping(self.q, self.config, require_all_totals=True)
        workflow.verify_totals(ui, self.q, self.config)
        ui.values["MamDollar"] = "0.00"
        with self.assertRaisesRegex(legacy.AutomationError, "tax"):
            workflow.verify_totals(ui, self.q, self.config)


if __name__ == "__main__":
    unittest.main()
