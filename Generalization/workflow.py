"""Checkpointed entry, verification, draft completion and optional handoff."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from RoshElectroptics.rosh_thorlabs_tafnit import (
    AutomationError, Checkpoint, is_customs_attachment, leave_final_confirmation,
)
from .configuration import Config, unverified_totals, validate_mapping
from .desktop import live_number, quote_attachment, verify_rows
from .quotation import Quotation


STAGES = {"new", "preparing", "items", "saving", "customs", "draft_ready", "awaiting_user_confirmation"}


def verify_totals(ui: Any, q: Quotation, config: Config) -> None:
    mapping = config.currencies[q.currency]
    expected = q.exact_total.quantize(Decimal('.001'), rounding=ROUND_HALF_UP)
    if live_number(ui.value(mapping["net_total_field"])) != expected:
        raise AutomationError("Tafnit's net total does not match the verified item amounts.")
    if mapping["tax_total_field"] and live_number(ui.value(mapping["tax_total_field"])) != q.tax_total:
        raise AutomationError("Tafnit's tax total differs from the reviewed quotation.")
    if mapping["gross_total_field"]:
        actual = live_number(ui.value(mapping["gross_total_field"]))
        if actual.quantize(Decimal(1).scaleb(-q.currency_decimals), rounding=ROUND_HALF_UP) != q.total:
            raise AutomationError("Tafnit's gross total differs from the reviewed quotation.")


def run_entry(ui: Any, q: Quotation, pdf: Path, state: Checkpoint, config: Config,
              *, open_final_confirmation: bool = False) -> None:
    stage = state.data.get("stage")
    if stage == "awaiting_user_confirmation":
        raise AutomationError("Final confirmation was already requested; automatic resume is blocked. Inspect Tafnit's confirmation or validation message.")
    if stage not in STAGES:
        raise AutomationError("Unrecognized checkpoint stage.")
    validate_mapping(q, config, require_all_totals=open_final_confirmation)
    request = ui.value("COM")
    if ui.value("STTS") != "0":
        raise AutomationError("The request is no longer New; it will not be edited or resubmitted.")
    if stage == "new" and request:
        raise AutomationError("Start with a NEW BLANK requisition.")
    if state.data.get("request") and request != state.data["request"]:
        raise AutomationError("Visible requisition does not match this checkpoint.")
    if request and not state.data.get("request") and stage != "saving":
        raise AutomationError("Checkpoint has no saved requisition number; reopen the original form.")
    if stage in ("new", "preparing"):
        state.update(stage="preparing")
        ui.prepare(q, pdf)
        state.update(stage="items")
    ui.verify_header(q)
    count = verify_rows(q, ui.item_rows(), config, complete=False)
    recorded_rows = state.data.get("rows", 0)
    if type(recorded_rows) is not int or recorded_rows < 0 or count < recorded_rows:
        raise AutomationError("Previously checkpointed rows are missing; inspect the request before resuming.")
    if stage in ("saving", "customs", "draft_ready") and count != len(q.items):
        raise AutomationError("A saved-stage request must already contain every reviewed item.")
    # COM may still be blank, or a crash after KSAVE may precede recording it.
    # Establish attachment identity before adding rows, saving or adopting COM.
    ui.click("NISPAH")
    attachments = ui.attachment_rows()
    customs_count = sum(is_customs_attachment(row) for row in attachments)
    if (sum(quote_attachment(row, q.number) for row in attachments) != 1
            or customs_count > int(config.customs["required"])
            or len(attachments) != 1 + customs_count):
        raise AutomationError("Request attachments do not identify this quotation; entry is blocked.")
    state.update(rows=count)
    if count < len(q.items):
        ui.begin_items(count + 1)
        for line, item in enumerate(q.items[count:], count + 1):
            state.update(stage="items", pending_line=line)
            ui.enter_item(item, line)
            state.update(rows=line, pending_line=None)
    verify_rows(q, ui.item_rows(), config)
    state.update(stage="saving")
    request = ui.save()
    state.update(stage="customs", request=request)
    if config.customs["required"]:
        ui.ensure_customs(state)
        ui.save()
    ui.click("NISPAH")
    attachments = ui.attachment_rows()
    customs_count = sum(is_customs_attachment(row) for row in attachments)
    expected_customs = int(config.customs["required"])
    if (len(attachments) != 1 + expected_customs or customs_count != expected_customs
            or sum(quote_attachment(row, q.number) for row in attachments) != 1):
        raise AutomationError("Saved attachments differ from the expected quotation/customs documents.")
    # Recheck saved rows too: header and save operations may trigger calculations.
    verify_rows(q, ui.item_rows(), config)
    verify_totals(ui, q, config)
    ui.verify_header(q)
    state.update(stage="draft_ready", unverified_totals=unverified_totals(q, config))
    if open_final_confirmation:
        leave_final_confirmation(ui, state)
        # No UI calls, reads, inputs, or retry after the handoff.
