"""Local quotation interchange, exact amount checks, and known-format parsing."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote, urlsplit


class QuotationError(ValueError):
    """A quotation needs correction or review before it can be entered."""


ITEM_FIELDS = ("part_number", "description", "quantity", "unit", "unit_price",
               "discount_percent", "line_total")
ITEM_FIELDS_WITH_WEBSITE = ITEM_FIELDS + ("website",)
QUOTE_FIELDS = {"schema_version", "vendor_name", "number", "date", "currency",
                "currency_decimals", "payment_terms", "notes", "net_total",
                "tax_total", "total", "items"}


def text(value: Any, label: str, *, blank: bool = False) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise QuotationError(f"{label} must be text without control characters.")
    value = " ".join(value.split())
    if (not value and not blank) or len(value) > 4000:
        raise QuotationError(f"{label} is blank or too long.")
    return value


def decimal(value: Any, label: str, places: int) -> Decimal:
    # No floats, ambiguous thousands/decimal separators, exponents, or NaN.
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,12}(?:\.\d{1,12})?", value):
        raise QuotationError(f"{label} must be a nonnegative decimal string, e.g. '1234.56'.")
    result = Decimal(value)
    if result != result.quantize(Decimal(1).scaleb(-places)):
        raise QuotationError(f"{label} exceeds the supported {places} decimal places.")
    return result


def website_url(value: Any, label: str = "website") -> str:
    value = text(value, label, blank=True)
    if not value:
        return ""
    try:
        parts = urlsplit(value)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None
                or any(c.isspace() for c in value)):
            raise ValueError()
        parts.port  # Reject malformed ports as well.
    except ValueError as exc:
        raise QuotationError(f"{label} must be a full http:// or https:// URL without credentials or spaces.") from exc
    return value


def object_keys(data: Any, expected: set[str], label: str) -> None:
    if not isinstance(data, dict) or set(data) != expected:
        raise QuotationError(f"{label} must have exactly these keys: {', '.join(sorted(expected))}.")


def read_json(path: Path) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise QuotationError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)
    except (OSError, ValueError) as exc:
        raise QuotationError(f"Cannot read {path}: {exc}") from exc


@dataclass(frozen=True)
class Item:
    part_number: str
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    discount_percent: Decimal
    line_total: Decimal
    website: str = ""

    @property
    def exact_amount(self) -> Decimal:
        return self.quantity * self.unit_price * (1 - self.discount_percent / 100)

    @property
    def tafnit_description(self) -> str:
        # Same legacy transport substitutions as Rosh's QuoteItem. Preserve the
        # source description for review and use this for both entry/readback.
        return self.description.replace("≥", ">=").replace("≤", "<=").replace("Ø", "dia. ")


@dataclass(frozen=True)
class Quotation:
    schema_version: int
    vendor_name: str
    number: str
    date: str
    currency: str
    currency_decimals: int
    payment_terms: str
    notes: str
    net_total: Decimal
    tax_total: Decimal
    total: Decimal
    items: tuple[Item, ...]

    @property
    def exact_total(self) -> Decimal:
        return sum((item.exact_amount for item in self.items), Decimal(0))

    @property
    def tafnit_date(self) -> str:
        return date.fromisoformat(self.date).strftime("%d/%m/%Y")

    def to_dict(self) -> dict:
        data = json.loads(json.dumps(asdict(self), default=str))
        for item in data["items"]:
            if not item["website"]:
                del item["website"]  # Keep existing no-website checkpoints compatible.
        return data


def parse_quotation(data: Any) -> Quotation:
    object_keys(data, QUOTE_FIELDS, "Quotation")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise QuotationError("schema_version must be 1.")
    places = data["currency_decimals"]
    if type(places) is not int or places not in (0, 1, 2, 3):
        raise QuotationError("currency_decimals must be an integer from 0 to 3.")
    currency = text(data["currency"], "currency")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise QuotationError("Use an uppercase three-letter currency, e.g. USD, EUR, ILS.")
    quote_date = text(data["date"], "date")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", quote_date):
            raise ValueError()
        date.fromisoformat(quote_date)
    except ValueError as exc:
        raise QuotationError("date must be a valid YYYY-MM-DD date.") from exc
    rows = data["items"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise QuotationError("Expected 1 to 1000 item rows.")
    quantum = Decimal(1).scaleb(-places)
    items = []
    for line, row in enumerate(rows, 1):
        label = f"Line {line}"
        expected_fields = ITEM_FIELDS_WITH_WEBSITE if isinstance(row, dict) and "website" in row else ITEM_FIELDS
        object_keys(row, set(expected_fields), label)
        item = Item(text(row["part_number"], label + " part number", blank=True),
                    text(row["description"], label + " description"),
                    decimal(row["quantity"], label + " quantity", 3),
                    text(row["unit"], label + " unit"),
                    decimal(row["unit_price"], label + " unit price", 3),
                    decimal(row["discount_percent"], label + " discount", 2),
                    decimal(row["line_total"], label + " amount", places),
                    website_url(row.get("website", ""), label + " website"))
        if item.quantity <= 0 or item.discount_percent > 100:
            raise QuotationError(f"{label}: quantity must be positive and discount at most 100%.")
        if item.exact_amount.quantize(quantum, rounding=ROUND_HALF_UP) != item.line_total:
            raise QuotationError(f"{label}: quantity × original price × discount does not match line_total.")
        items.append(item)
    net = decimal(data["net_total"], "net_total", places)
    tax = decimal(data["tax_total"], "tax_total", places)
    total = decimal(data["total"], "total", places)
    if sum((item.line_total for item in items), Decimal(0)) != net:
        raise QuotationError("Sum of line_total values does not match net_total; include freight as a line.")
    if net + tax != total:
        raise QuotationError("net_total + tax_total must equal total.")
    return Quotation(1, text(data["vendor_name"], "vendor_name"), text(data["number"], "number"),
                     quote_date, currency, places, text(data["payment_terms"], "payment_terms", blank=True),
                     text(data["notes"], "notes", blank=True), net, tax, total, tuple(items))


def load_quotation(path: Path, csv_path: Path | None = None) -> Quotation:
    data = read_json(path)
    if csv_path is not None:
        if not isinstance(data, dict) or data.get("items") != []:
            raise QuotationError("Set JSON items to [] when using --items-csv; do not supply two item sources.")
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames not in (list(ITEM_FIELDS), list(ITEM_FIELDS_WITH_WEBSITE)):
                raise QuotationError("CSV header must be: " + ",".join(ITEM_FIELDS) + "; optionally append ,website")
            rows = list(reader)
        if any(set(row) != set(reader.fieldnames) or any(v is None for v in row.values()) for row in rows):
            raise QuotationError("CSV contains missing or extra cells.")
        data["items"] = rows
    return parse_quotation(data)


def export_csv(q: Quotation, path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        columns = ITEM_FIELDS_WITH_WEBSITE if any(item.website for item in q.items) else ITEM_FIELDS
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(q.to_dict()["items"])


def read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise QuotationError("Encrypted PDFs are unsupported; provide an unlocked local copy.")
        return "\f".join(page.extract_text() or "" for page in reader.pages)
    except QuotationError:
        raise
    except Exception as exc:
        raise QuotationError("Cannot extract this PDF. Supply an accessible PDF and reviewed --data JSON.") from exc


def parse_known_pdf_text(source: str) -> Quotation:
    from RoshElectroptics.rosh_thorlabs_tafnit import parse_quote_text, QuoteError
    try:
        old = parse_quote_text(source)
    except QuoteError as exc:
        raise QuotationError("No validated local parser accepted this PDF: " + str(exc)) from exc
    from datetime import datetime
    parts = [re.sub(r"\s+\((?:[A-Z ]*WH|UK)\)$", "", i.part_number) for i in old.items]
    adjusted = [f"{i.part_number} -> {part}" for i, part in zip(old.items, parts) if i.part_number != part]
    notes = f"Vendor reference: {old.vendor_reference}."
    if adjusted:
        notes += " Rosh warehouse suffix normalization: " + "; ".join(adjusted) + "."
    return parse_quotation({
        "schema_version": 1, "vendor_name": "THORLABS INC", "number": old.number,
        "date": datetime.strptime(old.date, "%d/%m/%Y").strftime("%Y-%m-%d"),
        "currency": "USD", "currency_decimals": 2, "payment_terms": old.payment_terms,
        "notes": notes,
        "net_total": str(old.total), "tax_total": "0", "total": str(old.total),
        "items": [{"part_number": part, "description": i.description,
                   "quantity": str(i.quantity), "unit": "PCS", "unit_price": str(i.unit_price),
                   "discount_percent": str(i.discount), "line_total": str(i.extended_price),
                   "website": "https://www.thorlabs.com/item/" + url_quote(i.part_number.split(" ", 1)[0], safe="")}
                  for i, part in zip(old.items, parts)],
    })


def write_templates(directory: Path, source: str) -> None:
    """Exclusive creation preserves any edits from an earlier failed parse."""
    template = {"schema_version": 1, "vendor_name": "", "number": "", "date": "",
                "currency": "", "currency_decimals": 2, "payment_terms": "", "notes": "",
                "net_total": "", "tax_total": "", "total": "", "items": []}
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in [("quotation.template.local.json", json.dumps(template, indent=2) + "\n"),
                          ("items.template.csv", ",".join(ITEM_FIELDS_WITH_WEBSITE) + "\n"),
                          ("extracted.local.txt", source or "No selectable text; transcribe the scanned quotation locally.\n")]:
        try:
            with (directory / name).open("x", encoding="utf-8") as stream:
                stream.write(content)
        except FileExistsError:
            pass
