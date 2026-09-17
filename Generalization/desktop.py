"""Vendor-independent adapter for the observed Tafnit purchase-request form.

Only low-level window/DOM/input, attachment-save and image helpers are inherited.
Supplier assumptions, currencies, item classification and customs text are local
to this adapter. Importing this module does not load desktop drivers.
"""
from __future__ import annotations

import json
import re
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable

from RoshElectroptics.rosh_thorlabs_tafnit import (
    AutomationError, Checkpoint, TafnitDesktop, is_customs_attachment, normal,
)
from .configuration import Config, Supplier
from .quotation import Item, Quotation


def live_number(value: str) -> Decimal:
    value = normal(value)
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", value):
        raise AutomationError(f"Unrecognized Tafnit numeric format: {value!r}.")
    return Decimal(value.replace(",", ""))


def same_label(actual: str, expected: str) -> bool:
    return normal(actual).casefold() == normal(expected).casefold()


def same_description(actual: str, expected: str) -> bool:
    return re.sub(r"\s+", "", actual) == re.sub(r"\s+", "", expected)


def quote_line_remarks(q: Quotation, item: Item, line: int) -> str:
    return f"Quote {q.number}, line {line}: {item.part_number} - {item.tafnit_description}"


def quote_attachment(row: str, number: str) -> bool:
    return bool(re.search(r"(?:^|\s)" + re.escape("Quote " + number) + r"(?:\s|$)", normal(row)))


def verify_rows(q: Quotation, rows: list[list[str]], config: Config, *, complete: bool = True,
                read_catalog_details: Callable[[int], dict] | None = None) -> int:
    if len(rows) > len(q.items) or (complete and len(rows) != len(q.items)):
        raise AutomationError(f"Expected {len(q.items)} item rows; Tafnit has {len(rows)}.")
    for line, (item, cells) in enumerate(zip(q.items, rows), 1):
        if len(cells) != 12 or normal(cells[11]) != str(line):
            raise AutomationError(f"Unrecognized Tafnit table or sequence at line {line}.")
        for name, index, expected in [
            ("quantity", 6, item.quantity), ("unit price", 3, item.unit_price),
            ("discount", 5, item.discount_percent),
            ("amount", 2, item.exact_amount.quantize(Decimal('.001'), rounding=ROUND_HALF_UP)),
        ]:
            if live_number(cells[index]) != expected:
                raise AutomationError(f"Line {line}: Tafnit {name} differs from the reviewed quotation.")
        if not any(same_label(cells[4], label) for label in config.currencies[q.currency]["row_labels"]):
            raise AutomationError(f"Line {line}: currency differs from {q.currency}.")
        if not any(same_label(cells[8], label) for label in config.units[item.unit]["row_labels"]):
            raise AutomationError(f"Line {line}: unit differs from {item.unit}.")
        if normal(cells[10]):
            if not item.part_number or normal(cells[7]) != item.part_number:
                raise AutomationError(f"Line {line}: catalog part does not match the reviewed part number.")
        if not same_description(cells[9], item.tafnit_description):
            # A locked catalog description is acceptable only with the exact
            # quoted configuration read back from this saved line's remarks.
            if not normal(cells[10]) or read_catalog_details is None:
                raise AutomationError(f"Line {line}: description differs from the reviewed quotation.")
            details = read_catalog_details(line)
            expected = {"ln": str(line), "Cat": normal(cells[10]),
                        "CatSpk": item.part_number, "Lbb3": item.part_number,
                        "Remarks": quote_line_remarks(q, item, line)}
            if (not isinstance(details, dict)
                    or any(not isinstance(details.get(k), str) or normal(details[k]) != normal(v)
                           for k, v in expected.items())
                    or not isinstance(details.get("DescLarge"), str)
                    or not normal(details["DescLarge"])
                    or not same_description(details["DescLarge"], cells[9])):
                raise AutomationError(f"Line {line}: saved catalog identity or quotation remarks differ from the reviewed quotation.")
    return len(rows)


class GeneralDesktop(TafnitDesktop):
    def __init__(self, artifacts: Path, config: Config, supplier: Supplier, quote: Quotation,
                 *, allow_open_request: bool = True):
        self.supplier = supplier
        self.quote = quote
        super().__init__(artifacts, config, allow_open_request=allow_open_request)

    def _verify_fields(self, expected: dict[str, str]) -> None:
        fields = json.dumps(list(expected))
        actual = self.reader.read(f"Object.fromEntries({fields}.map(k=>[k,document.getElementById(k)?.value]))")
        for field, value in expected.items():
            found = actual.get(field)
            matches = same_label(str(found), value) if field == "HSPK" else normal(str(found)) == normal(value)
            if found is None or not matches:
                raise AutomationError(f"Tafnit field {field} does not match the reviewed supplier/configuration.")

    def verify_supplier(self) -> None:
        self._verify_fields({"SPK": self.supplier.code, "HSPK": self.supplier.name,
                             "SOCHEN": self.supplier.agent_code})

    def verify_header(self, q: Quotation) -> None:
        self._verify_fields(dict(self.config.header,
                                 SUGD=self.config.request_type_code, MHTD=self.config.purpose_code,
                                 KM=self.config.currencies[q.currency]["code"], SEIF="",
                                 SPK=self.supplier.code, HSPK=self.supplier.name,
                                 SOCHEN=self.supplier.agent_code, REMARKINS=self.config.budget_note))

    def prepare(self, q: Quotation, pdf: Path) -> None:
        self._verify_fields(self.config.header)
        if self.value("SEIF"):
            raise AutomationError("This adapter expects a funding note and a blank budget-number field.")
        self.select("SUGD", self.config.request_type_code)
        self.select("MHTD", self.config.purpose_code)
        self.fill("KM", self.config.currencies[q.currency]["code"])
        self.click("SUPPLIER")
        self.fill("SPK", self.supplier.code)
        if self.value("SOCHEN") != self.supplier.agent_code:
            self.fill("SOCHEN", self.supplier.agent_code)
        self.verify_supplier()
        self.click("KLALI")
        self.fill("REMARKINS", self.config.budget_note)
        self.click("REMARKS")
        self.fill("REMARKSPK", f"Per quote {q.number} dated {q.tafnit_date}. Payment terms: {q.payment_terms}.")
        self.fill("SpecialRemarks1", q.notes)
        self.fill("SpecialRemarks2", f"Quote {q.number}; {q.vendor_name}; {q.currency}.")
        self.attach_quote(q, pdf)

    def attach_quote(self, q: Quotation, pdf: Path) -> None:
        self.click("NISPAH")
        rows = self.attachment_rows()
        matches = [row for row in rows if quote_attachment(row, q.number)]
        if len(matches) == 1 and len(rows) == 1:
            self.close_archive()
            return  # A crash may have followed a successful upload.
        if rows:
            raise AutomationError("Unexpected existing attachments during preparation; inspect the request.")
        self.click("BOpenArchiveUtilWin")
        self.fill("DESC", f"Quote {q.number}")
        self.select("SUGMM", "2")
        self.click("BUploadFile")
        self.template("bechar kovets")
        self.p.hotkey("alt", "n")
        self.clipboard.copy(str(pdf.resolve()))
        self.p.hotkey("ctrl", "v")
        self.p.press("enter")
        time.sleep(1)
        self.template("ishur - upload", minimal_confidence=.97, relative_position=(.8, .5))
        time.sleep(2)
        self.main.activate()
        rows = self.attachment_rows()
        if len(rows) != 1 or not quote_attachment(rows[0], q.number):
            raise AutomationError("Expected exactly the uploaded quotation attachment.")
        self.close_archive()

    def close_archive(self) -> None:
        visible = self.reader.read("(()=>{let e=document.getElementById('ArchiveUtilWin');return !!e&&getComputedStyle(e).visibility!=='hidden'})()")
        if visible:
            self.click_selector('#ArchiveUtilWin img[onclick*="CloseArchiveUtilWin"]')

    def read_item_details(self, line: int) -> dict:
        """Open a saved row through its line-number link; do not edit or save it."""
        self.click("ITEMS")
        self.click("PRITIM")
        self.click_selector(f'tr[key="{line}"] [id="wbglngrid"]')
        fields = ["ln", "Cat", "CatSpk", "Lbb3", "DescLarge", "Remarks"]
        details = self.reader.read(f"Object.fromEntries({json.dumps(fields)}.map(k=>[k,document.getElementById(k)?.value]))")
        self.click("PRITIM")
        return details

    def enter_item(self, item: Item, line: int) -> None:
        self.click("ITEMS")
        self.click("PRITIM2")
        if self.value("ln") != str(line):
            raise AutomationError(f"Expected empty item row {line}.")
        # Avoid carrying a catalog selection into a line with no supplier SKU.
        if self.value("Cat") or self.value("CatSpk"):
            raise AutomationError("The new item row still has a catalog selection; inspect or clear it manually.")
        if item.part_number:
            self.fill("CatSpk", item.part_number)
            time.sleep(1)
        catalog = self.value("Cat")
        if catalog and not catalog.isdigit():
            raise AutomationError("Unexpected Tafnit catalog identifier.")
        # A supplier SKU can cover several configurations (length, connectors,
        # etc.). Preserve the quotation even when Tafnit locks the catalog text.
        locked_description = None
        if catalog:
            if not item.part_number or self.value("Lbb3") != item.part_number:
                raise AutomationError(f"Catalog manufacturer part does not match the reviewed part on line {line}.")
            description = self.element('[id="DescLarge"]')
            if description["readonly"]:
                locked_description = description["value"]
                if not normal(locked_description):
                    raise AutomationError(f"Line {line} has an empty locked catalog description.")
                if not same_description(locked_description, item.tafnit_description):
                    self.fill("Remarks", quote_line_remarks(self.quote, item, line))
        if locked_description is None:
            self.fill("DescLarge", item.tafnit_description)
        if not catalog:
            self.select("KitlugFLD0A", self.config.classification["category_code"])
            self.select("KitlugFLD0B", self.config.classification["subcategory_code"])
        if self.config.unit_field:
            unit = self.element(f'[id={json.dumps(self.config.unit_field)}]')
            code = self.config.units[item.unit]["code"]
            if unit["options"]:
                self.select(self.config.unit_field, code)
            else:
                self.fill(self.config.unit_field, code)
        # Some catalogued rows also require WebSite. Preserve a resolved catalog
        # link; an uncatalogued row may still carry a stale previous-item URL.
        if not catalog or not self.value("WebSite"):
            website = item.website or self.supplier.website
            if not website:
                raise AutomationError(f"Line {line} has no website. Supply an item website or supplier fallback before entry, or complete this draft manually.")
            self.fill("WebSite", website)
        # Catalog/classification/unit lookups happen before financial fields.
        self.fill("Quan", item.quantity, numeric=True)
        self.fill("Coin", self.config.currencies[self.quote.currency]["code"])
        self.fill("Scm", item.unit_price, numeric=True)
        self.fill("Pre", item.discount_percent, numeric=True)
        if self.value("CatSpk") != item.part_number:
            raise AutomationError(f"Supplier part number changed on line {line}.")
        self.screenshot(f"row-{line:03d}-before-save")
        self.click("KSVLIN")
        time.sleep(2)
        if self.value("ln") != str(line + 1):
            raise AutomationError(f"Line {line} did not advance; inspect Tafnit's warning.")

    def ensure_customs(self, state: Checkpoint) -> None:
        if not self.config.customs["required"]:
            return
        self.click("NISPAH")
        customs = [row for row in self.attachment_rows() if is_customs_attachment(row)]
        if customs:
            if len(customs) == 1 and (state.data.get("customs_verified") or state.data.get("customs_fields_verified")):
                state.update(customs_verified=True)
                return
            raise AutomationError("Unexpected customs declaration; inspect it before resuming.")
        self.click("KNISCUSTOM")
        self.template("tafnit - tofes yadani button")
        self.p.hotkey("ctrl", "a")
        self.clipboard.copy(self.config.customs["description"])
        self.p.hotkey("ctrl", "v")
        self.verify_focused_text(self.config.customs["description"])
        self.template("tafnit - items usage", secondary_template="tafnit - left boundary items usage",
                      secondary_template_direction="left", relative_position=(-1.0, .4))
        self.p.hotkey("ctrl", "a")
        self.clipboard.copy(self.config.customs["usage"])
        self.p.hotkey("ctrl", "v")
        self.verify_focused_text(self.config.customs["usage"])
        state.update(customs_fields_verified=True)
        self.p.scroll(-300)
        self.template("tafnit - customs - confirm")  # Document save, not requisition approval.
        time.sleep(2)
        self.main.activate()
        if len([r for r in self.attachment_rows() if is_customs_attachment(r)]) != 1:
            raise AutomationError("Expected one generated customs attachment.")
        state.update(customs_verified=True)
