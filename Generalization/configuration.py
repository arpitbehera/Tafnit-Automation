"""Explicit institution/form mappings and interactive registered-supplier input."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .quotation import Quotation, QuotationError, object_keys, read_json, text, website_url


class ConfigurationError(ValueError):
    pass


HEADER_FIELDS = {"MEHKAR", "IZAM", "MHLK", "Building", "Floor", "Room",
                 "CBuilding", "CFloor", "CRoom"}
CONFIG_FIELDS = {"tafnit_host", "header", "budget_note", "request_type_code", "purpose_code",
                 "currencies", "unit_field", "units", "classification", "customs"}


@dataclass(frozen=True)
class Config:
    tafnit_host: str
    header: dict[str, str]
    budget_note: str
    request_type_code: str
    purpose_code: str
    currencies: dict[str, dict]
    unit_field: str
    units: dict[str, dict]
    classification: dict[str, str]
    customs: dict


@dataclass(frozen=True)
class Supplier:
    code: str
    name: str
    agent_code: str
    website: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        if not self.website:
            del data["website"]  # Preserve fingerprints of existing supplier selections.
        return data


def _field(value: Any, label: str, *, blank: bool = False) -> str:
    value = text(value, label, blank=blank)
    if value and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise ConfigurationError(f"{label} must be a DOM field ID, not a selector or JavaScript.")
    return value


def _labels(value: Any, label: str, *, blank: bool = False) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{label} needs at least one exact table label.")
    return [text(v, label, blank=blank) for v in value]


def parse_config(data: Any) -> Config:
    try:
        object_keys(data, CONFIG_FIELDS, "Configuration")
        host = text(data["tafnit_host"], "tafnit_host")
        if not re.fullmatch(r"[a-zA-Z0-9.-]+", host):
            raise ConfigurationError("tafnit_host must be a hostname without a scheme or path.")
        object_keys(data["header"], HEADER_FIELDS, "header")
        header = {k: text(v, k) for k, v in data["header"].items()}
        currencies = {}
        if not isinstance(data["currencies"], dict) or not data["currencies"]:
            raise ConfigurationError("Configure at least one currency.")
        for iso, mapping in data["currencies"].items():
            if not re.fullmatch(r"[A-Z]{3}", iso):
                raise ConfigurationError("Currency keys must be uppercase ISO-style codes.")
            object_keys(mapping, {"code", "row_labels", "net_total_field", "tax_total_field", "gross_total_field"}, iso)
            currencies[iso] = {"code": text(mapping["code"], iso + " code"),
                               "row_labels": _labels(mapping["row_labels"], iso + " labels"),
                               "net_total_field": _field(mapping["net_total_field"], iso + " net field"),
                               "tax_total_field": _field(mapping["tax_total_field"], iso + " tax field", blank=True),
                               "gross_total_field": _field(mapping["gross_total_field"], iso + " gross field", blank=True)}
        unit_field = _field(data["unit_field"], "unit_field", blank=True)
        if unit_field in {"Coin", "Scm", "Pre", "Quan", "Cat", "CatSpk", "DescLarge", "ln"}:
            raise ConfigurationError("unit_field cannot overwrite another item field.")
        if not isinstance(data["units"], dict) or not data["units"]:
            raise ConfigurationError("Configure at least one unit.")
        units = {}
        for name, mapping in data["units"].items():
            object_keys(mapping, {"code", "row_labels"}, "unit " + name)
            units[text(name, "unit")] = {"code": text(mapping["code"], "unit code", blank=not unit_field),
                                          "row_labels": _labels(mapping["row_labels"], "unit labels", blank=True)}
            if not unit_field and mapping["code"]:
                raise ConfigurationError("A unit code requires unit_field.")
        if not unit_field and len(units) != 1:
            raise ConfigurationError("Without unit_field only one verified default unit can be mapped.")
        object_keys(data["classification"], {"category_code", "subcategory_code"}, "classification")
        classification = {k: text(v, k) for k, v in data["classification"].items()}
        object_keys(data["customs"], {"required", "description", "usage"}, "customs")
        customs = data["customs"]
        if type(customs["required"]) is not bool:
            raise ConfigurationError("customs.required must be a JSON boolean.")
        customs = {"required": customs["required"],
                   "description": text(customs["description"], "customs description", blank=not customs["required"]),
                   "usage": text(customs["usage"], "customs usage", blank=not customs["required"])}
        return Config(host, header, text(data["budget_note"], "budget_note"),
                      text(data["request_type_code"], "request_type_code"),
                      text(data["purpose_code"], "purpose_code"), currencies,
                      unit_field, units, classification, customs)
    except QuotationError as exc:
        raise ConfigurationError(str(exc)) from exc


def load_config(path: Path) -> Config:
    try:
        return parse_config(read_json(path))
    except QuotationError as exc:
        raise ConfigurationError(str(exc)) from exc


def unverified_totals(quote: Quotation, config: Config) -> list[str]:
    mapping = config.currencies[quote.currency]
    return [name for name in ("tax", "gross") if not mapping[name + "_total_field"]]


def validate_mapping(quote: Quotation, config: Config, *, require_all_totals: bool = False) -> None:
    if quote.currency not in config.currencies:
        raise ConfigurationError(f"No verified Tafnit mapping for currency {quote.currency}.")
    for item in quote.items:
        if item.unit not in config.units:
            raise ConfigurationError(f"No verified Tafnit mapping for unit {item.unit!r}.")
    currency = config.currencies[quote.currency]
    if quote.tax_total and (not currency["tax_total_field"] or not currency["gross_total_field"]):
        raise ConfigurationError("Nonzero tax requires tax_total_field and gross_total_field readback mappings.")
    if require_all_totals and unverified_totals(quote, config):
        raise ConfigurationError("Opening final confirmation requires verified tax and gross total-field mappings, even for zero tax.")


def prompt_supplier(vendor_name: str, *, ask: Callable[[str], str] = input) -> Supplier:
    print(f"Quotation invoice recipient: {vendor_name}")
    try:
        code = text(ask("Registered Tafnit supplier code (not a VAT/tax ID): "), "supplier code")
        name = text(ask("Exact supplier name displayed by Tafnit: "), "supplier name")
        agent = text(ask("Tafnit agent code (Enter if none): "), "agent code", blank=True)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", code) or (agent and not re.fullmatch(r"[A-Za-z0-9_-]+", agent)):
            raise ConfigurationError("Supplier/agent codes may contain only letters, digits, underscores and hyphens.")
        website = website_url(ask("Supplier website fallback (full URL; Enter to rely on item/catalog links): "), "supplier website")
        return Supplier(code, name, agent, website)
    except QuotationError as exc:
        raise ConfigurationError(str(exc)) from exc
