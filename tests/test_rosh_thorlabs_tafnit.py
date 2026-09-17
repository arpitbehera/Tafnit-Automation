"""Financial parsing and workflow regression tests; never operate the desktop."""
import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


HEADER = """Rosh Electroptics Ltd.
Quote Date: 01/01/30
Price Quote (EX-WORK) FDTEST
Please issue the order to:
Thorlabs Inc.
Vendor's Reference: WTEST
Payment Terms: 30 DAYS
Attn: Researcher
Tel.: 000-0000000
Ln Part Number and Description
Quantity Unit Price Discount
Extended Price
"""
QUOTE = HEADER + '''1 DEMO-CUBE
30 mm Cage Cube (USA) 5.00 PCS USD 10.01 10.00% 9.01 45.05
2 DEMO-PLATE 1.00 PCS USD 2.25 10.00% 2.03 2.03\f''' + HEADER + '''"Alignment plate,
orange (CHN)"
TOTAL USD 47.08
ק"ג16הערכת משקל
'''


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.find_spec("RoshElectroptics.rosh_thorlabs_tafnit")
        if spec:
            cls.m = importlib.import_module("RoshElectroptics.rosh_thorlabs_tafnit")
        else:
            cls.m = None

    def module(self):
        self.assertIsNotNone(self.m, "The PDF automation module is not implemented")
        return self.m

    def test_original_prices_and_cross_page_description(self):
        q = self.module().parse_quote_text(QUOTE)
        self.assertEqual(q.number, "FDTEST")
        self.assertEqual(q.items[0].unit_price, Decimal("10.01"))
        self.assertEqual(q.items[0].discount, Decimal("10"))
        self.assertEqual(q.items[1].description, '"Alignment plate, orange (CHN)"')
        self.assertEqual(q.total, Decimal("47.08"))
        self.assertEqual(q.exact_total, Decimal("47.070"))
        self.assertEqual(q.weight_kg, Decimal("16"))

    def test_bad_line_amount_stops_before_gui(self):
        with self.assertRaisesRegex(self.module().QuoteError, "line 1"):
            self.m.parse_quote_text(QUOTE.replace("45.05", "45.06"))

    def test_bad_total_is_rejected(self):
        with self.assertRaisesRegex(self.module().QuoteError, "total"):
            self.m.parse_quote_text(QUOTE.replace("47.08", "350.00"))

    def test_skipped_row_is_rejected(self):
        with self.assertRaisesRegex(self.module().QuoteError, "sequence"):
            self.m.parse_quote_text(QUOTE.replace("2 DEMO-PLATE", "3 DEMO-PLATE"))

    def test_mixed_currency_is_rejected(self):
        with self.assertRaisesRegex(self.module().QuoteError, "USD"):
            self.m.parse_quote_text(QUOTE.replace("USD 2.25", "EUR 2.25"))

    def test_other_invoice_recipient_is_rejected(self):
        with self.assertRaisesRegex(self.module().QuoteError, "Thorlabs"):
            self.m.parse_quote_text(QUOTE.replace("Thorlabs Inc.", "Different Supplier"))

    def test_missing_price_is_not_silently_skipped(self):
        bad = QUOTE.replace("5.00 PCS USD 10.01 10.00% 9.01 45.05", "price unavailable")
        with self.assertRaisesRegex(self.module().QuoteError, "line 1"):
            self.m.parse_quote_text(bad)

    def test_warehouse_suffix_and_country_not_in_description(self):
        text = HEADER + '''1 DEMO-B (DE WH)
Achromatic Fiber Collimator
DEU
1.00 PCS USD 100.01 10.00% 90.01 90.01
TOTAL USD 90.01'''
        q = self.module().parse_quote_text(text)
        self.assertEqual(q.items[0].part_number, "DEMO-B (DE WH)")
        self.assertEqual(q.items[0].description, "Achromatic Fiber Collimator")

    def test_table_verification_catches_catalog_price_overrides(self):
        m = self.module()
        self.assertTrue(hasattr(m, "verify_rows"), "Table verification is not implemented")
        q = m.parse_quote_text(QUOTE)
        rows = [
            ["", "135.135", "45.045", "10.010", "$ ארהב", "10.00", "5.000", "", "", q.items[0].description, "", "1"],
            ["", "6.075", "2.025", "2.250", "$ ארהב", "10.00", "1.000", "", "", q.items[1].description, "", "2"],
        ]
        self.assertEqual(m.verify_rows(q, rows), 2)
        rows[0][3] = "9.01"  # Accidental use of the already-discounted unit price.
        with self.assertRaisesRegex(m.AutomationError, "price"):
            m.verify_rows(q, rows)

    def test_same_price_different_item_is_rejected(self):
        m = self.module()
        q = m.parse_quote_text(QUOTE)
        row = ["", "135.135", "45.045", "10.010", "$", "10", "5", "", "", "Wrong item", "", "1"]
        with self.assertRaisesRegex(m.AutomationError, "description"):
            m.verify_rows(q, [row], complete=False)
        row[7], row[10] = "WRONG-SKU", "123456"
        with self.assertRaisesRegex(m.AutomationError, "part"):
            m.verify_rows(q, [row], complete=False)

    def test_description_comparison_preserves_inequalities_in_legacy_text(self):
        m = self.module()
        q = m.parse_quote_text(QUOTE.replace("30 mm Cage Cube (USA)", "Adapter ≥12 mm, ≤20 mm"))
        row = ["", "135.135", "45.045", "10.010", "$", "10", "5", "", "",
               "Adapter >=12 mm, <=20 mm", "", "1"]
        self.assertEqual(m.verify_rows(q, [row], complete=False), 1)
        self.assertEqual(q.items[0].description, "Adapter ≥12 mm, ≤20 mm")
        row[9] = "Adapter ?12 mm, ?20 mm"
        with self.assertRaisesRegex(m.AutomationError, "description"):
            m.verify_rows(q, [row], complete=False)

    def test_diameter_notation_survives_legacy_description_storage(self):
        m = self.module()
        q = m.parse_quote_text(QUOTE.replace("30 mm Cage Cube (USA)", "Adapter for Ø12 mm"))
        row = ["", "135.135", "45.045", "10.010", "$", "10", "5", "", "",
               "Adapter for dia. 12 mm", "", "1"]
        self.assertEqual(q.items[0].tafnit_description, "Adapter for dia. 12 mm")
        self.assertEqual(q.items[0].description, "Adapter for Ø12 mm")
        self.assertEqual(m.verify_rows(q, [row], complete=False), 1)
        row[9] = "Adapter for ?12 mm"
        with self.assertRaisesRegex(m.AutomationError, "description"):
            m.verify_rows(q, [row], complete=False)

    def test_catalog_verification_recognizes_rosh_uk_source_note(self):
        m = self.module()
        q = m.parse_quote_text(QUOTE.replace("1 DEMO-CUBE", "1 DEMO-CUBE (UK)"))
        row = ["", "135.135", "45.045", "10.010", "$", "10", "5", "DEMO-CUBE",
               "", "Catalog description", "12345", "1"]
        self.assertEqual(m.verify_rows(q, [row], complete=False), 1)
        self.assertEqual(q.items[0].part_number, "DEMO-CUBE (UK)")
        row[7] = "DEMO-CUBE/M"
        with self.assertRaisesRegex(m.AutomationError, "catalog part"):
            m.verify_rows(q, [row], complete=False)
        q = m.parse_quote_text(QUOTE.replace("1 DEMO-CUBE", "1 DEMO-CUBE (LEFT)"))
        row[7] = "DEMO-CUBE"
        with self.assertRaisesRegex(m.AutomationError, "catalog part"):
            m.verify_rows(q, [row], complete=False)

    def test_resume_rejects_different_pdf(self):
        m = self.module()
        self.assertTrue(hasattr(m, "Checkpoint"), "Checkpoint recovery is not implemented")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            state = m.Checkpoint(p, "hash-a", resume=False)
            state.update(stage="items", rows=1)
            with self.assertRaisesRegex(m.AutomationError, "different PDF"):
                m.Checkpoint(p, "hash-b", resume=True)

    def test_customs_recognizes_legacy_visual_hebrew(self):
        m = self.module()
        self.assertTrue(m.is_customs_attachment("\tסכמל הרהצה ספוט\tסכמל הרהצה"))
        self.assertTrue(m.is_customs_attachment("הצהרה למכס"))
        self.assertFalse(m.is_customs_attachment("Quote FDTEST"))

    def test_resume_uses_live_rows_and_stops_at_confirmation(self):
        m = self.module()
        q = m.parse_quote_text(QUOTE)
        actions = []
        class Ui:
            rows = [["", "135.135", "45.045", "10.010", "$", "10", "5", "", "", q.items[0].description, "", "1"]]
            def value(self, field):
                return {"COM": "", "STTS": "0", "NetoDollar": "47.070"}[field]
            def item_rows(self):
                return self.rows
            def verify_header(self, quote, note):
                actions.append("verify-header")
            def begin_items(self, line):
                actions.append(("begin", line))
            def enter_item(self, item):
                actions.append(("enter", item.line))
                self.rows.append(["", "6.075", "2.025", "2.250", "$", "10", "1", "", "", q.items[1].description, "", "2"])
            def save(self):
                actions.append("save")
                return "123"
            def ensure_customs(self, state):
                actions.append("customs")
            def click(self, name):
                actions.append(name)
            def attachment_rows(self):
                return ["Quote FDTEST", "סכמל הרהצה ספוט"]
            def open_final_confirmation(self):
                actions.append("handoff")
        with tempfile.TemporaryDirectory() as d:
            state = m.Checkpoint(Path(d) / "state.json", "hash-a", resume=False)
            # A crash happened after Tafnit accepted row 1, before checkpointing.
            state.update(stage="items", rows=0, pending_line=1)
            m.run_entry(Ui(), q, Path("quote.pdf"), state, "Example lab funding note")
            self.assertEqual([a for a in actions if isinstance(a, tuple)], [("begin", 2), ("enter", 2)])
            self.assertEqual(actions[-1], "handoff")
            self.assertEqual(state.data["stage"], "awaiting_user_confirmation")
            with self.assertRaisesRegex(m.AutomationError, "handoff"):
                m.run_entry(Ui(), q, Path("quote.pdf"), state, "Example lab funding note")

    def test_preexisting_order_cannot_be_used_for_a_new_run(self):
        m = self.module()
        class ExistingOrder:
            def value(self, field):
                return {"COM": "1234567", "STTS": "0"}[field]
        with tempfile.TemporaryDirectory() as d:
            state = m.Checkpoint(Path(d) / "state.json", "hash-a", resume=False)
            with self.assertRaisesRegex(m.AutomationError, "NEW BLANK"):
                m.run_entry(ExistingOrder(), m.parse_quote_text(QUOTE), Path("quote.pdf"), state, "Example lab funding note")

    def test_save_time_description_corruption_blocks_final_handoff(self):
        m = self.module()
        q = m.parse_quote_text(QUOTE)
        rows = [
            ["", "135.135", "45.045", "10.010", "$", "10", "5", "", "", q.items[0].description, "", "1"],
            ["", "6.075", "2.025", "2.250", "$", "10", "1", "", "", q.items[1].description, "", "2"],
        ]
        handoffs = []

        def save():
            rows[0][9] = "Corrupted after save"
            return "123"

        ui = SimpleNamespace(
            value=lambda field: {"COM": "", "STTS": "0", "NetoDollar": "47.070"}[field],
            verify_header=lambda quote, note: None, item_rows=lambda: rows,
            save=save, ensure_customs=lambda state: None, click=lambda name: None,
            attachment_rows=lambda: ["Quote FDTEST", "סכמל הרהצה ספוט"],
            open_final_confirmation=lambda: handoffs.append(True),
        )
        with tempfile.TemporaryDirectory() as d:
            state = m.Checkpoint(Path(d) / "state.json", "hash-a", resume=False)
            state.update(stage="items")
            with self.assertRaisesRegex(m.AutomationError, "description"):
                m.run_entry(ui, q, Path("quote.pdf"), state, "Funding note")
            self.assertEqual(handoffs, [])
            self.assertNotEqual(state.data["stage"], "awaiting_user_confirmation")

    def test_failed_final_click_is_not_retried_on_resume(self):
        m = self.module()
        class FailedUi:
            def open_final_confirmation(self):
                raise m.AutomationError("Lost window")
        with tempfile.TemporaryDirectory() as d:
            state = m.Checkpoint(Path(d) / "state.json", "hash-a", resume=False)
            with self.assertRaisesRegex(m.AutomationError, "Lost window"):
                m.leave_final_confirmation(FailedUi(), state)
            self.assertEqual(state.data["stage"], "awaiting_user_confirmation")

    def test_final_handoff_never_confirms_or_touches_browser_after_submit(self):
        m = self.module()
        self.assertTrue(hasattr(m, "leave_final_confirmation"), "Final handoff is not implemented")
        actions = []
        class Ui:
            def open_final_confirmation(self):
                actions.append("open-final-confirmation")
        with tempfile.TemporaryDirectory() as d:
            state = m.Checkpoint(Path(d) / "state.json", "hash-a", resume=False)
            m.leave_final_confirmation(Ui(), state)
            self.assertEqual(actions, ["open-final-confirmation"])
            self.assertEqual(json.loads(state.path.read_text())["stage"], "awaiting_user_confirmation")


class DesktopTests(unittest.TestCase):
    def test_save_handles_unmounted_archive_description_after_page_reload(self):
        from RoshElectroptics import rosh_thorlabs_tafnit as app
        for description in (None, "", "Quote FDTEST"):
            with self.subTest(description=description):
                actions = []
                ui = object.__new__(app.TafnitDesktop)
                ui.reader = SimpleNamespace(read=lambda expression: description)

                def value(field):
                    if field == "DESC":
                        if description is None:
                            raise app.AutomationError("Missing Tafnit field DESC.")
                        return description
                    self.assertEqual(field, "COM")
                    return "12345"

                ui.value = value
                ui.click = actions.append
                ui.fill = lambda field, text: actions.append((field, text))
                ui.click_selector = lambda selector: actions.append("close-archive")
                ui.screenshot = lambda name: None
                with patch.object(app.time, "sleep"):
                    self.assertEqual(ui.save(), "12345")
                self.assertEqual(actions[-1], "KSAVE")
                if description == "":
                    self.assertEqual(actions[:2], ["NISPAH", "BOpenArchiveUtilWin"])
                    self.assertIn(("DESC", "Quotation and customs documents"), actions)
                else:
                    self.assertEqual(actions, ["KSAVE"])

    def test_uncatalogued_item_has_product_website_before_row_save(self):
        from RoshElectroptics import rosh_thorlabs_tafnit as app
        item = app.QuoteItem(1, "DEMO-B (DE WH)", "Collimator ≥1 mm", Decimal("2"),
                             Decimal("100"), Decimal("10"), Decimal("180"))
        values = {"ln": "1", "Cat": "", "WebSite": ""}
        saved = []
        ui = object.__new__(app.TafnitDesktop)
        ui.value = lambda field: values.get(field, "")
        ui.fill = lambda field, value, **kwargs: values.update({field: str(value)})
        ui.select = lambda field, value: values.update({field: value})
        ui.screenshot = lambda name: None

        def click(name):
            if name == "KSVLIN":
                self.assertEqual(values["WebSite"],
                                 "https://www.thorlabs.com/item/DEMO-B")
                saved.append(dict(values))
                values["ln"] = "2"

        ui.click = click
        with patch.object(app.time, "sleep"):
            ui.enter_item(item)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["CatSpk"], "DEMO-B (DE WH)")
        self.assertEqual(saved[0]["DescLarge"], "Collimator >=1 mm")
        self.assertEqual(saved[0]["Scm"], "100")
        self.assertEqual(saved[0]["Pre"], "10")

    def test_catalogued_item_fills_missing_website_and_preserves_existing_link(self):
        from RoshElectroptics import rosh_thorlabs_tafnit as app
        item = app.QuoteItem(1, "DEMO-B", "Quote text", Decimal("2"),
                             Decimal("100"), Decimal("10"), Decimal("180"))
        for existing in ("", "https://www.thorlabs.com/catalog-product"):
            with self.subTest(existing=existing):
                values = {"ln": "1", "Cat": "12345", "WebSite": existing,
                          "DescLarge": "Resolved catalog description"}
                ui = object.__new__(app.TafnitDesktop)
                ui.value = lambda field: values.get(field, "")
                ui.fill = lambda field, value, **kwargs: values.update({field: str(value)})
                ui.screenshot = lambda name: None

                def click(name):
                    if name == "KSVLIN":
                        self.assertEqual(values["WebSite"], existing or
                                         "https://www.thorlabs.com/item/DEMO-B")
                        values["ln"] = "2"

                ui.click = click
                with patch.object(app.time, "sleep"):
                    ui.enter_item(item)
                self.assertEqual(values["DescLarge"], "Resolved catalog description")


if __name__ == "__main__":
    unittest.main()
