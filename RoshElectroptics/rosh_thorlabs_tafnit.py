"""Enter a Rosh/Thorlabs PDF quotation in Tafnit; NEVER confirm final submission.

Windows: uv run RoshElectroptics/rosh_thorlabs_tafnit.py "D:\\path\\quotation.pdf"
Preview: add --dry-run to validate without operating the desktop.
Live entry starts at the logged-in Tafnit home screen or a blank purchase request.

See ROSH_THORLAB_TAFNIT.md for setup, recovery, and the supported PDF format.
Imports and --dry-run do not operate the desktop or read login credentials.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

CUSTOMS_TEXT = "Optical components for use in an optics research laboratory"
PURCHASE_REQUEST_LABEL = "דרישה לרכש"
CENT = Decimal("0.01")
NUMBER = r"\d[\d,]*(?:\.\d+)?"


class QuoteError(ValueError):
    """The PDF cannot be used without resolving a discrepancy."""


class AutomationError(RuntimeError):
    """Stop without repeating an uncertain desktop action."""


@dataclass(frozen=True)
class UserConfig:
    """Institution and personal settings, loaded only from a local JSON file."""
    tafnit_host: str
    supplier_code: str
    agent_code: str
    research_group: str
    requester: str
    department: str
    building: str
    floor: str
    room: str
    contact_building: str
    contact_floor: str
    contact_room: str
    budget_note: str


def load_config(path: Path) -> UserConfig:
    if not path.is_file():
        raise AutomationError(f"Missing local config: {path}. Copy config.example.json to config.local.json and fill in your settings.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AutomationError(f"Cannot read config: {path}") from exc
    required = {field.name for field in fields(UserConfig)}
    if not isinstance(data, dict) or set(data) != required:
        raise AutomationError("Config must contain exactly the keys in config.example.json.")
    for key, value in data.items():
        if not isinstance(value, str) or not value.strip():
            raise AutomationError(f"Config field {key} must be a non-blank string.")
    data = {key: value.strip() for key, value in data.items()}
    if not re.fullmatch(r"[a-zA-Z0-9.-]+", data["tafnit_host"]):
        raise AutomationError("tafnit_host must be a hostname without https:// or a path.")
    return UserConfig(**data)


def number(value: str) -> Decimal:
    try:
        result = Decimal(value.replace(",", "").strip())
    except InvalidOperation as exc:
        raise QuoteError(f"Invalid number: {value!r}") from exc
    if not result.is_finite():
        raise QuoteError(f"Non-finite number: {value!r}")
    return result


def normal(value: str) -> str:
    return " ".join(value.split())


def is_customs_attachment(row: str) -> bool:
    # Tafnit's legacy archive grid exposes visually ordered Hebrew in innerText.
    return any(label in normal(row) for label in ("הצהרה למכס", "סכמל הרהצה"))


@dataclass(frozen=True)
class QuoteItem:
    line: int
    part_number: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    extended_price: Decimal

    @property
    def exact_amount(self) -> Decimal:
        return self.quantity * self.unit_price * (1 - self.discount / 100)

    @property
    def tafnit_description(self) -> str:
        # Tafnit's legacy text transport replaces these Unicode signs with '?'.
        return self.description.replace("≥", ">=").replace("≤", "<=").replace("Ø", "dia. ")


@dataclass(frozen=True)
class Quote:
    number: str
    date: str
    vendor_reference: str
    payment_terms: str
    phone: str
    weight_kg: Decimal | None
    total: Decimal
    items: tuple[QuoteItem, ...]

    @property
    def exact_total(self) -> Decimal:
        return sum((i.exact_amount for i in self.items), Decimal(0))


def parse_quote_text(text: str) -> Quote:
    """Parse pypdf's plain text from Rosh's Priority EX-WORK quotation.

    Page headers are removed before joining item blocks: Priority can put an
    item's amounts on one page and its description on the following page.
    Rounded discounted unit prices are checked but NEVER used as input prices.
    """
    if "Rosh Electroptics" not in text:
        raise QuoteError("Expected a Rosh Electroptics quotation with selectable text.")
    if not re.search(r"Please issue the order to:\s*Thorlabs Inc\.", text, re.I):
        raise QuoteError("The order recipient must be Thorlabs Inc.")

    def required(pattern: str, label: str) -> str:
        m = re.search(pattern, text, re.I)
        if not m:
            raise QuoteError(f"Cannot read {label} from the PDF.")
        return normal(m.group(1))

    quote_numbers = set(re.findall(r"Price Quote\s*\([^)]*\)\s*(\S+)", text))
    if len(quote_numbers) != 1:
        raise QuoteError("Expected exactly one quotation number across all pages.")
    quote_date = required(r"Quote Date:\s*(\d{2}/\d{2}/\d{2,4})", "quote date")
    try:
        date = datetime.strptime(quote_date, "%d/%m/%y" if len(quote_date) == 8 else "%d/%m/%Y")
    except ValueError as exc:
        raise QuoteError("Invalid quote date") from exc
    total_match = re.findall(rf"\bTOTAL\s+([A-Z]{{3}})\s+({NUMBER})", text)
    if len(total_match) != 1 or total_match[0][0] != "USD":
        raise QuoteError("Expected one USD total; mixed currency and other currencies are unsupported.")
    total = number(total_match[0][1])
    bodies = []
    for page in text.split("\f"):
        if "Part Number and Description" not in page:
            continue  # Terms-only page.
        header_end = page.find("Extended Price")
        if header_end < 0:
            raise QuoteError("Unrecognized item-table header.")
        body = page[header_end + len("Extended Price"):]
        body = re.split(r"\bTOTAL\s+[A-Z]{3}", body, maxsplit=1)[0]
        body = re.sub(r"© Created in Priority[^\n]*", "", body)
        bodies.append(body)
    table = "\n".join(bodies).replace("\r", "")
    starts = list(re.finditer(
        r"(?m)^\s*(\d+) +([A-Z][A-Za-z0-9./_-]*(?: +\([A-Z ]+\))?)(?=\s|$)", table))
    if not starts:
        raise QuoteError("No item rows found. Scans and other quotation layouts are unsupported.")
    amounts_pattern = re.compile(
        rf"({NUMBER})\s+PCS\s+([A-Z]{{3}})\s+({NUMBER})\s+({NUMBER})\s*%\s+({NUMBER})\s+({NUMBER})")
    items = []
    for pos, start in enumerate(starts):
        line = int(start.group(1))
        if line != pos + 1:
            raise QuoteError(f"Item sequence is not consecutive at line {line}.")
        end = starts[pos + 1].start() if pos + 1 < len(starts) else len(table)
        block = table[start.end():end]
        matches = list(amounts_pattern.finditer(block))
        if len(matches) != 1:
            raise QuoteError(f"Cannot read exactly one set of prices for line {line}.")
        amounts = matches[0]
        qty, currency, price, discount, discounted, extended = amounts.groups()
        if currency != "USD":
            raise QuoteError(f"Only USD is supported (line {line}: {currency}).")
        description = block[:amounts.start()] + " " + block[amounts.end():]
        description = re.sub(r"(?m)^\s*[A-Z]{3}\s*$", "", description)
        description = normal(description)
        item = QuoteItem(line, normal(start.group(2)), description, number(qty),
                         number(price), number(discount), number(extended))
        if not description or item.quantity <= 0 or item.unit_price < 0 or not 0 <= item.discount <= 100:
            raise QuoteError(f"Invalid description, quantity, price, or discount on line {line}.")
        discounted_exact = item.unit_price * (1 - item.discount / 100)
        if discounted_exact.quantize(CENT, rounding=ROUND_HALF_UP) != number(discounted):
            raise QuoteError(f"Discounted unit price mismatch on line {line}.")
        if item.exact_amount.quantize(CENT, rounding=ROUND_HALF_UP) != item.extended_price:
            raise QuoteError(f"Extended price mismatch on line {line}.")
        items.append(item)
    if sum((i.extended_price for i in items), Decimal(0)) != total:
        raise QuoteError("The sum of the printed item amounts does not match the PDF total.")
    weight = None
    for line in text.splitlines():
        if "משקל" in line and ('ק"ג' in line or "ק״ג" in line or "kg" in line.lower()):
            nums = re.findall(NUMBER, line)
            if len(nums) == 1:
                weight = number(nums[0])
    phone_match = re.search(r"Attn:[^\n]*\nTel\.:\s*([\d+ -]+)", text)
    return Quote(quote_numbers.pop(), date.strftime("%d/%m/%Y"),
                 required(r"Vendor's Reference:\s*([^\n]+)", "vendor reference"),
                 required(r"Payment Terms:\s*([^\n]+)", "payment terms"),
                 re.sub(r"\D", "", phone_match.group(1)) if phone_match else "",
                 weight, total, tuple(items))


def load_quote(path: Path) -> Quote:
    from pypdf import PdfReader
    reader = PdfReader(path)
    # Plain mode handles the rotated text in supported Priority quotations.
    return parse_quote_text("\f".join(page.extract_text() for page in reader.pages))


def export_items(quote: Quote, path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "description", "quantity", "price", "discount"])
        for item in quote.items:
            writer.writerow([item.part_number, item.description, item.quantity,
                             item.unit_price, item.discount])


def verify_rows(quote: Quote, rows: list[list[str]], *, complete: bool = True) -> int:
    """Check the actual RTL Tafnit item table, not just its grand total.

    Columns follow the inspected Tafnit table: cancel, NIS amount,
    currency amount, original price, currency, discount, quantity, manufacturer
    part, unit, description, catalog number, row number.
    """
    if len(rows) > len(quote.items) or (complete and len(rows) != len(quote.items)):
        raise AutomationError(f"Expected {len(quote.items)} item rows; Tafnit has {len(rows)}.")
    for item, cells in zip(quote.items, rows):
        if len(cells) != 12 or normal(cells[-1]) != str(item.line):
            raise AutomationError(f"Unrecognized table layout or row sequence at line {item.line}.")
        for label, actual, expected in [
            ("quantity", cells[6], item.quantity), ("price", cells[3], item.unit_price),
            ("discount", cells[5], item.discount),
            ("line amount", cells[2], item.exact_amount.quantize(Decimal('.001'), rounding=ROUND_HALF_UP)),
        ]:
            if number(actual) != expected:
                raise AutomationError(f"Line {item.line} {label}: Tafnit {actual!r}, quote {expected}.")
        if "$" not in cells[4] and "USD" not in cells[4]:
            raise AutomationError(f"Line {item.line} is not in USD.")
        if normal(cells[10]):
            # Catalog rows display a manufacturer part and Tafnit's own text.
            # Rosh appends warehouse notes and the UK source note to the SKU.
            part = re.sub(r"\s+\((?:[A-Z ]*WH|UK)\)$", "", item.part_number)
            if normal(cells[7]) != part:
                raise AutomationError(f"Line {item.line} catalog part does not match {item.part_number}.")
        elif re.sub(r"\s+", "", cells[9]) != re.sub(r"\s+", "", item.tafnit_description):
            # Uncatalogued rows leave the manufacturer column blank. Their
            # description is from the quote; line wrapping can split words.
            raise AutomationError(f"Line {item.line} description does not match the quotation.")
    return len(rows)


class Checkpoint:
    def __init__(self, path: Path, fingerprint: str, *, resume: bool):
        self.path = path
        if path.exists():
            if not resume:
                raise AutomationError(f"A run already exists at {path}. Use --resume after reviewing Tafnit.")
            self.data = json.loads(path.read_text(encoding="utf-8"))
            if self.data.get("pdf_sha256") != fingerprint:
                raise AutomationError("This checkpoint belongs to a different PDF.")
        elif resume:
            raise AutomationError(f"Cannot resume: no checkpoint at {path}.")
        else:
            self.data = {"pdf_sha256": fingerprint, "stage": "new", "rows": 0, "request": ""}
            self.update()

    def update(self, **changes: Any) -> None:
        self.data.update(changes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)


def leave_final_confirmation(ui: Any, state: Checkpoint) -> None:
    # Persist BEFORE clicking: even a crash must not cause a second submission.
    state.update(stage="awaiting_user_confirmation")
    ui.open_final_confirmation()
    # Deliberately no browser reads, keystrokes, dialog dismissal, or retry here.


class ChromeReader:
    """Read live DOM through Chrome's undocked Console, using existing login.

    No remote-debugging profile, credentials, or undocumented Tafnit HTTP calls.
    The console commands are generated by this script and typed (not pasted).
    They read fields/coordinates; data entry uses ordinary mouse and keyboard.
    """
    def __init__(self, main_window: Any):
        import pyautogui
        import pyperclip
        self.p = pyautogui
        self.clipboard = pyperclip
        self.main = main_window

    def read(self, expression: str) -> Any:
        import uuid
        token = "ROSH_" + uuid.uuid4().hex + ":"
        command = ("try{copy(" + json.dumps(token) + "+JSON.stringify({ok:true,data:(" +
                   expression + ")}))}catch(e){copy(" + json.dumps(token) +
                   "+JSON.stringify({ok:false,error:String(e)}))}")
        # Escape Unicode in JS literals, since pyautogui.write uses key codes.
        command = command.encode("ascii", "backslashreplace").decode("ascii")
        self.main.activate()
        self.p.hotkey("ctrl", "l")  # Bypass Tafnit's own keyboard shortcuts.
        self.p.hotkey("ctrl", "shift", "j")
        deadline = time.monotonic() + 8
        dev = None
        while time.monotonic() < deadline:
            active = self.p.getActiveWindow()
            if active and active.title.startswith("DevTools - "):
                dev = active
                break
            time.sleep(.2)
        if dev is None:
            raise AutomationError("Undock Chrome DevTools into a separate window, select Console, then retry.")
        try:
            dev.activate()
            dev.moveTo(100, 100)
            dev.resizeTo(1000, 700)
            time.sleep(.25)
            self.p.hotkey("ctrl", "l")  # Clear Console and return to its prompt.
            self.p.click(dev.left + 70, dev.top + dev.height - 37)
            self.clipboard.copy(token + "pending")
            self.p.write(command, interval=.001)
            self.p.press("enter")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                value = self.clipboard.paste()
                if value.startswith(token) and value != token + "pending":
                    result = json.loads(value[len(token):])
                    if not result["ok"]:
                        raise AutomationError(result["error"])
                    return result.get("data")
                time.sleep(.1)
            raise AutomationError("Chrome Console did not return data. No further desktop actions were taken.")
        finally:
            dev.close()
            self.main.activate()

    def viewport_origin(self) -> tuple[int, int]:
        """Locate Chrome's rendering surface using Windows, not guessed offsets."""
        import ctypes
        from ctypes import wintypes
        # Own function bindings: pygetwindow uses its own RECT class on the
        # shared ctypes.windll instance. Changing that instance breaks it.
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        candidates = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def visit(handle, _):
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(handle, name, 256)
            if name.value == "Chrome_RenderWidgetHostHWND" and user32.IsWindowVisible(handle):
                rect = wintypes.RECT()
                user32.GetWindowRect(handle, ctypes.byref(rect))
                if rect.right - rect.left > 500 and rect.bottom - rect.top > 400:
                    candidates.append((rect.left, rect.top))
            return True

        user32.EnumChildWindows(wintypes.HWND(self.main._hWnd), visit, 0)
        if len(set(candidates)) != 1:
            raise AutomationError("Cannot uniquely locate Chrome's page surface; check the Tafnit window.")
        return candidates[0]


class TafnitDesktop:
    """Normal UI input with DOM readback; every wait is bounded."""
    def __init__(self, artifacts: Path, config: UserConfig, *, allow_open_request: bool = True):
        if os.name != "nt":
            raise AutomationError("Desktop entry needs Windows Python, not WSL Python. --dry-run works anywhere.")
        import pyautogui as p
        import pyperclip
        self.p, self.clipboard = p, pyperclip
        p.FAILSAFE = True
        p.PAUSE = .08
        self.artifacts = artifacts
        self.config = config
        chrome = self.chrome_windows()
        windows = [w for w in chrome if self.is_request_window(w)]
        if not windows:
            if not allow_open_request:
                raise AutomationError("To resume, reopen the original purchase request; a new request will not be opened.")
            windows = [w for w in chrome if any(label in w.title.casefold()
                       for label in ("tafnit", "תפנית", config.tafnit_host.casefold()))]
            # Some installations use only the institution name as the title.
            # A lone Chrome window is usable only after verifying its host.
            if not windows and len(chrome) == 1:
                windows = chrome
        if len(windows) != 1:
            raise AutomationError("Keep exactly one Tafnit home screen or purchase-request window open in Chrome on display 1.")
        self.bind_window(windows[0])
        info = self.page_info()
        self.check_page_setup(info)
        if info["request"] is None:
            if not allow_open_request:
                raise AutomationError("To resume, reopen the original purchase request.")
            # A request window still loading is not a home-screen menu.
            if self.is_request_window(self.main):
                raise AutomationError("The purchase-request form has not loaded. Wait for it before resuming.")
            self.open_purchase_request()
        elif not info["form"] or not self.is_request_window(self.main):
            raise AutomationError("The selected window is not a supported Tafnit purchase request.")

    def chrome_windows(self) -> list[Any]:
        return [w for w in self.p.getAllWindows() if "Google Chrome" in w.title]

    @staticmethod
    def is_request_window(window: Any) -> bool:
        return PURCHASE_REQUEST_LABEL in window.title or "purchase request" in window.title.casefold()

    def bind_window(self, window: Any) -> None:
        self.main = window
        self.main.activate()
        self.main.maximize()
        if self.main.left > 0:
            raise AutomationError("Move Tafnit to display 1 before running the script.")
        self.reader = ChromeReader(self.main)

    def page_info(self) -> dict:
        return self.reader.read("""({host:location.hostname,dpr:devicePixelRatio,
          request:document.getElementById('COM')?.value??null,
          status:document.getElementById('STTS')?.value??null,
          form:['COM','STTS','SUGD','MHTD','KM'].every(id=>!!document.getElementById(id))})""")

    def check_page_setup(self, info: dict) -> None:
        if info["host"].casefold() != self.config.tafnit_host.casefold():
            raise AutomationError("The selected Chrome window is not on the configured Tafnit host.")
        self.dpr = info["dpr"]
        if tuple(self.p.size()) != (2560, 1440) or self.dpr != 1:
            raise AutomationError("Use the tested display-1 setup: 2560x1440, Windows scaling 100%, Chrome zoom 100%.")

    def visible_controls(self, selector: str) -> list[dict]:
        """Read visible controls and unique CSS paths without activating them."""
        return self.reader.read("""(()=>{
          const visible=e=>e.getClientRects().length&&
            !['hidden','collapse'].includes(getComputedStyle(e).visibility)&&
            !e.matches(':disabled')&&e.getAttribute('aria-disabled')!=='true';
          const path=e=>{const parts=[];while(e&&e.nodeType===1){
            parts.unshift(e.localName+':nth-child('+([...e.parentNode.children].indexOf(e)+1)+')');
            e=e.parentElement;}return parts.join(' > ');};
          return [...document.querySelectorAll(SELECTOR)].filter(visible).map(e=>({
            selector:path(e),text:e.innerText||e.value||e.getAttribute('aria-label')||
              e.getAttribute('alt')||e.title||''}));
        })()""".replace("SELECTOR", json.dumps(selector)))

    def controls_with_text(self, text: str) -> list[str]:
        controls = self.visible_controls('a,button,input[type="button"],input[type="submit"],'
                                         '[role="button"],[role="menuitem"],[onclick]')
        matches = [c["selector"] for c in controls
                   if normal(re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", c["text"])) == text]
        # A link nested inside a clickable menu row represents one choice.
        return [s for s in matches if not any(other.startswith(s + " > ") for other in matches)]

    def purchase_request_control(self) -> str | None:
        choices = self.controls_with_text(PURCHASE_REQUEST_LABEL)
        if len(choices) > 1:
            raise AutomationError(f"Expected exactly one visible '{PURCHASE_REQUEST_LABEL}' option; the menu is ambiguous.")
        return choices[0] if choices else None

    def open_purchase_menu(self) -> str:
        """Follow kalirkosh's Hebrew → Initiator → Hebrew → Entry menu path."""
        self.template("ivrit - main", relative_position=(.5, .3))
        self.template("yazam", relative_position=(-.5, .3))
        self.template("ivrit - secondary")
        self.template("klita")
        # Clear the hover highlight as in kalirkosh, outside the failsafe corner.
        self.p.moveTo(2, 2)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            choice = self.purchase_request_control()
            if choice:
                return choice
            time.sleep(.5)
        raise AutomationError(f"The home-screen menu did not show exactly '{PURCHASE_REQUEST_LABEL}'. Inspect the menu before resuming.")

    def open_purchase_request(self) -> None:
        choice = self.purchase_request_control() or self.open_purchase_menu()
        previous_handles = {w._hWnd for w in self.chrome_windows()}
        self.click_selector(choice)  # Exactly one click; never retry creation.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            opened = [w for w in self.chrome_windows() if w._hWnd not in previous_handles]
            if len(opened) > 1:
                raise AutomationError("Multiple Chrome windows opened; inspect Tafnit before resuming.")
            if opened and opened[0]._hWnd != self.main._hWnd:
                self.bind_window(opened[0])
            info = self.page_info()
            if info["host"]:  # An about:blank popup may still be loading.
                self.check_page_setup(info)
                if info["form"]:
                    if not self.is_request_window(self.main):
                        raise AutomationError(f"The opened window is not a '{PURCHASE_REQUEST_LABEL}' purchase request.")
                    if normal(info["request"]) or info["status"] != "0":
                        raise AutomationError("The opened purchase request must be NEW BLANK before entry.")
                    return
            time.sleep(.5)
        raise AutomationError(f"'{PURCHASE_REQUEST_LABEL}' did not open a blank form in time. Check Chrome popup blocking and Tafnit; reopen the original form before --resume.")

    def value(self, field: str) -> str:
        result = self.reader.read(f"document.getElementById({json.dumps(field)})?.value")
        if result is None:
            raise AutomationError(f"Missing Tafnit field {field}.")
        return str(result).strip()

    def element(self, selector: str) -> dict:
        expression = """(()=>{const e=document.querySelector(SELECTOR);
          if(!e)throw Error('Missing control: '+SELECTOR);
          if(getComputedStyle(e).visibility==='hidden'||!e.getClientRects().length)
            throw Error('Control is hidden: '+SELECTOR);
          e.scrollIntoView({block:'nearest',inline:'nearest'});
          const r=e.getBoundingClientRect();
          return {x:r.x+r.width/2,y:r.y+r.height/2,value:e.value||'',
            disabled:!!e.disabled,readonly:!!e.readOnly,
            options:e.options?[...e.options].map(o=>({value:o.value,text:o.text})):[],
            maxlength:e.maxLength};})()""".replace("SELECTOR", json.dumps(selector))
        result = self.reader.read(expression)
        if result["disabled"]:
            raise AutomationError(f"Tafnit has disabled {selector}.")
        ox, oy = self.reader.viewport_origin()
        result["point"] = (ox + round(result["x"] * self.dpr), oy + round(result["y"] * self.dpr))
        return result

    def click(self, name: str) -> None:
        self.click_selector(f'[name="{name}"]')

    def click_selector(self, selector: str) -> None:
        target = self.element(selector)
        self.p.click(*target["point"])
        time.sleep(.7)

    def fill(self, field: str, value: Any, *, numeric: bool = False) -> None:
        value = str(value)
        # ID selectors ignore case in Tafnit's quirks mode (e.g. Spk vs SPK).
        target = self.element(f'[id={json.dumps(field)}]')
        if target["readonly"]:
            raise AutomationError(f"Field {field} is read-only.")
        if target["maxlength"] and target["maxlength"] > 0 and len(value) > target["maxlength"]:
            raise AutomationError(f"{field} exceeds Tafnit's {target['maxlength']}-character limit.")
        self.p.click(*target["point"])
        self.p.hotkey("ctrl", "a")
        self.clipboard.copy(value)
        self.p.hotkey("ctrl", "v")
        self.p.press("tab")
        time.sleep(.4)
        actual = self.value(field)
        mismatch = number(actual) != number(value) if numeric else normal(actual) != normal(value)
        if mismatch:
            raise AutomationError(f"Readback failed for {field}: expected {value!r}, got {actual!r}.")

    def select(self, field: str, value: str) -> None:
        target = self.element(f'[id={json.dumps(field)}]')
        choices = [i for i, opt in enumerate(target["options"]) if opt["value"] == value]
        if len(choices) != 1:
            raise AutomationError(f"Cannot select {value!r} in {field}.")
        self.p.click(*target["point"])
        self.p.press("home")
        if choices[0]:
            self.p.press("down", presses=choices[0], interval=.03)
        self.p.press("enter")
        self.p.press("tab")
        time.sleep(.6)
        if self.value(field) != value:
            raise AutomationError(f"Selection did not stick: {field}={value}.")

    def screenshot(self, name: str) -> None:
        from PIL import ImageGrab
        ImageGrab.grab().save(self.artifacts / f"{name}.png")

    def template(self, name: str, *, click: bool = True, **kwargs) -> tuple:
        if __package__:
            from ._vendor import general_gui_controller as ggc
        else:
            from _vendor import general_gui_controller as ggc
        ggc.GENERAL_GUI_CONTROLLER_TEMPLATES_PATH = str(Path(__file__).parent / "templates")
        point = ggc.detect_template(name, max_waiting_time_seconds=20,
                                    warn_if_not_found=False, **kwargs)
        if point is None:
            raise AutomationError(f"Could not find {name!r}. Stopped; no blind click was made.")
        if click:
            self.p.click(*point)
            time.sleep(.7)
        return point

    def attachment_rows(self) -> list[str]:
        return self.reader.read("[...document.querySelectorAll('a#wbgFILE')].map(e=>e.closest('tr').innerText)")

    def verify_header(self, q: Quote, budget_note: str) -> None:
        config = self.config
        expected = {"SUGD": "4", "MHTD": "1", "KM": "1", "SEIF": "",
                    "MEHKAR": config.research_group, "IZAM": config.requester, "MHLK": config.department,
                    "SPK": config.supplier_code, "SOCHEN": config.agent_code, "REMARKINS": budget_note,
                    "Building": config.building, "Floor": config.floor, "Room": config.room,
                    "CBuilding": config.contact_building, "CFloor": config.contact_floor, "CRoom": config.contact_room}
        if q.phone:
            expected.update(PhoneNumber=q.phone, CPhoneNumber=q.phone)
        fields = json.dumps(list(expected))
        actual = self.reader.read(f"Object.fromEntries({fields}.map(k=>[k,document.getElementById(k)?.value]))")
        for field, value in expected.items():
            if actual.get(field) is None or normal(actual[field]) != normal(value):
                raise AutomationError(f"Request field {field} differs from the intended order: expected {value!r}, found {actual.get(field)!r}.")

    def prepare(self, q: Quote, pdf: Path, budget_note: str) -> None:
        self.select("SUGD", "4")
        self.select("MHTD", "1")
        self.fill("KM", "1", numeric=True)
        if self.value("SEIF"):
            raise AutomationError("The new request has a budget code. Clear it to use the configured funding note.")
        for field, expected in [("MEHKAR", self.config.research_group), ("IZAM", self.config.requester), ("MHLK", self.config.department)]:
            if self.value(field) != expected:
                raise AutomationError(f"Expected {field}={expected} from your local config. Check your Tafnit defaults.")
        self.click("SUPPLIER")
        self.fill("SPK", self.config.supplier_code)
        if "THORLABS" not in self.value("HSPK").upper() or self.value("SOCHEN") != self.config.agent_code:
            raise AutomationError("Supplier/agent did not resolve to THORLABS INC / Rosh Electroptics.")
        self.click("KLALI")
        self.fill("REMARKINS", budget_note)
        if q.phone:
            self.fill("PhoneNumber", q.phone)
            self.fill("CPhoneNumber", q.phone)
        self.click("REMARKS")
        self.fill("REMARKSPK", f"Per quote {q.number} dated {q.date}. Vendor reference {q.vendor_reference}. Payment terms: {q.payment_terms}.")
        weight = f"Approx. {q.weight_kg} kg per quote {q.number}." if q.weight_kg else "Weight not provided in quote."
        self.fill("SpecialRemarks1", weight + " Package dimensions not provided.")
        self.fill("SpecialRemarks2", f"Quote {q.number} dated {q.date}; vendor reference {q.vendor_reference}. Optics and optomechanics.")
        self.click("NISPAH")
        rows = self.attachment_rows()
        title = f"Quote {q.number}"
        if any(title in normal(row) for row in rows):
            return  # A prior interrupted upload is already present.
        if rows:
            raise AutomationError("Unexpected existing attachments. Check that this is the correct request.")
        self.click("BOpenArchiveUtilWin")
        self.fill("DESC", title)
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
        if not any(title in normal(row) for row in self.attachment_rows()):
            raise AutomationError("PDF upload has not appeared in the attachment list.")
        # Keep DESC populated: Tafnit validates this hidden archive field on Save.
        visible = self.reader.read("(()=>{let e=document.getElementById('ArchiveUtilWin');return !!e&&getComputedStyle(e).visibility!=='hidden'})()")
        if visible:
            self.click_selector('#ArchiveUtilWin img[onclick*="CloseArchiveUtilWin"]')

    def item_rows(self) -> list[list[str]]:
        self.click("ITEMS")
        self.click("PRITIM")
        return self.reader.read("[...document.querySelectorAll('tr[key]')].filter(r=>r.getClientRects().length&&getComputedStyle(r).visibility!=='hidden').map(r=>[...r.cells].map(c=>c.innerText.trim())).filter(c=>c.length===12&&/^\\d+$/.test(c[11])&&/[0-9]/.test(c[3]))")

    def begin_items(self, next_line: int) -> None:
        self.click("ITEMS")
        self.click("PRITIM2")
        self.click("KCLRLINE")  # Clears an unfinished entry, not a saved item row.
        if self.value("ln") != str(next_line):
            raise AutomationError(f"Expected new row {next_line}; inspect the item form before resuming.")

    def enter_item(self, item: QuoteItem) -> None:
        self.click("ITEMS")
        self.click("PRITIM2")
        if self.value("ln") != str(item.line):
            raise AutomationError(f"Expected blank item row {item.line}; Tafnit shows {self.value('ln')}.")
        # Catalog lookup MUST happen before prices, since it can overwrite them.
        self.fill("CatSpk", item.part_number)
        time.sleep(1)
        catalog = self.value("Cat")
        if not catalog:
            self.fill("DescLarge", item.tafnit_description)
        elif not catalog.isdigit():
            raise AutomationError(f"Unexpected catalog number {catalog!r}.")
        if not self.value("WebSite"):
            # Tafnit requires a website even for some catalogued items. Rosh's
            # parenthesized warehouse/country note is not part of the URL SKU.
            sku = item.part_number.split(" ", 1)[0]
            self.fill("WebSite", "https://www.thorlabs.com/item/" + url_quote(sku, safe=""))
        self.fill("Quan", item.quantity, numeric=True)
        self.fill("Coin", "1", numeric=True)
        self.fill("Scm", item.unit_price, numeric=True)
        self.fill("Pre", item.discount, numeric=True)
        if not catalog:
            self.select("KitlugFLD0A", "1")  # Scientific Equipment
            self.select("KitlugFLD0B", "7")  # Laboratory Instruments
        if self.value("CatSpk") != item.part_number:
            raise AutomationError(f"Supplier part number changed on row {item.line}.")
        self.screenshot(f"row-{item.line:03d}-before-save")
        self.click("KSVLIN")
        time.sleep(2)
        if self.value("ln") != str(item.line + 1):
            raise AutomationError(f"Row {item.line} did not advance. Resolve the visible Tafnit warning before resuming.")

    def save(self) -> str:
        # An interrupted upload can leave this hidden-but-required archive
        # metadata empty. Populate it through the visible attachment dialog.
        # After a page reload the dialog is not mounted, so DESC is absent and
        # is not part of Tafnit's save validation until the dialog is opened.
        description = self.reader.read("document.getElementById('DESC')?.value")
        if description is not None and not normal(description):
            self.click("NISPAH")
            self.click("BOpenArchiveUtilWin")
            self.fill("DESC", "Quotation and customs documents")
            self.click_selector('#ArchiveUtilWin img[onclick*="CloseArchiveUtilWin"]')
        self.click("KSAVE")
        time.sleep(2)
        request = self.value("COM")
        if not request.isdigit():
            raise AutomationError("Save did not produce a requisition number. Inspect Tafnit's message.")
        self.screenshot("saved-request")
        return request

    def ensure_customs(self, state: Checkpoint) -> None:
        self.click("NISPAH")
        customs = [row for row in self.attachment_rows() if is_customs_attachment(row)]
        if customs:
            if len(customs) == 1 and (state.data.get("customs_verified") or state.data.get("customs_fields_verified")):
                state.update(customs_verified=True)
                return
            raise AutomationError("A customs declaration already exists. Verify it or remove the old row before resuming; the script will not add a duplicate.")
        self.click("KNISCUSTOM")
        self.template("tafnit - tofes yadani button")
        self.p.hotkey("ctrl", "a")
        self.clipboard.copy(CUSTOMS_TEXT)
        self.p.hotkey("ctrl", "v")
        self.verify_focused_text(CUSTOMS_TEXT)
        self.template("tafnit - items usage", secondary_template="tafnit - left boundary items usage",
                      secondary_template_direction="left", relative_position=(-1.0, .4))
        self.p.hotkey("ctrl", "a")
        self.clipboard.copy(CUSTOMS_TEXT)
        self.p.hotkey("ctrl", "v")
        self.verify_focused_text(CUSTOMS_TEXT)
        state.update(customs_fields_verified=True)
        self.p.scroll(-300)
        self.template("tafnit - customs - confirm")  # Saves the document only.
        time.sleep(2)
        self.main.activate()
        rows = self.attachment_rows()
        if len([r for r in rows if is_customs_attachment(r)]) != 1:
            raise AutomationError("Expected one generated customs attachment.")
        state.update(customs_verified=True)

    def verify_focused_text(self, expected: str) -> None:
        self.p.hotkey("ctrl", "a")
        self.clipboard.copy("")
        self.p.hotkey("ctrl", "c")
        time.sleep(.15)
        if normal(self.clipboard.paste()) != normal(expected):
            raise AutomationError("The customs field did not retain the requested wording.")

    def open_final_confirmation(self) -> None:
        # KUPDT opens Tafnit's final research-use declaration. Do not click its
        # confirm button, press Enter, dismiss it, or inspect with DevTools after.
        self.click("KUPDT")
        time.sleep(3)
        self.screenshot("final-confirmation-for-user")


def run_entry(ui: Any, q: Quote, pdf: Path, state: Checkpoint, budget_note: str) -> None:
    """Resume only after checking the live request and all already entered rows."""
    if state.data["stage"] == "awaiting_user_confirmation":
        raise AutomationError("This run already reached the user-confirmation handoff. Check Tafnit; do not submit it again.")
    request = ui.value("COM")
    if ui.value("STTS") != "0":
        raise AutomationError("The request is no longer New. The script will not edit or resubmit it.")
    if state.data["stage"] == "new" and request:
        raise AutomationError("Start with a NEW BLANK requisition, not the order just placed.")
    if state.data.get("request") and request != state.data["request"]:
        raise AutomationError("The visible requisition does not match this checkpoint.")
    if request and not state.data.get("request") and state.data["stage"] != "saving":
        raise AutomationError("This checkpoint has no saved requisition number. Reopen its original unsaved form.")
    if state.data.get("budget_note", budget_note) != budget_note:
        raise AutomationError("The budget note changed since this run began.")
    if state.data["stage"] in ("new", "preparing"):
        state.update(stage="preparing", budget_note=budget_note)
        ui.prepare(q, pdf, budget_note)
        state.update(stage="items")
    ui.verify_header(q, budget_note)
    rows = ui.item_rows()
    count = verify_rows(q, rows, complete=False)
    state.update(rows=count)
    if count < len(q.items):
        ui.begin_items(count + 1)
        for item in q.items[count:]:
            state.update(stage="items", pending_line=item.line)
            print(f"Entering {item.line}/{len(q.items)}: {item.part_number}", flush=True)
            ui.enter_item(item)
            state.update(rows=item.line, pending_line=None)
    verify_rows(q, ui.item_rows())
    state.update(stage="saving")
    request = ui.save()
    state.update(stage="customs", request=request)
    ui.ensure_customs(state)
    ui.save()
    # Full-page saves can corrupt characters that survived field readback.
    verify_rows(q, ui.item_rows())
    ui.click("NISPAH")
    attachments = ui.attachment_rows()
    if (len(attachments) != 2
            or not any(f"Quote {q.number}" in normal(row) for row in attachments)
            or sum(is_customs_attachment(row) for row in attachments) != 1):
        raise AutomationError("Expected exactly the quote and one customs declaration before submission.")
    if number(ui.value("NetoDollar")) != q.exact_total.quantize(Decimal('.001'), rounding=ROUND_HALF_UP):
        raise AutomationError("Tafnit's saved USD total does not match the verified item amounts.")
    ui.verify_header(q, budget_note)
    print(f"Saved requisition {request}. Requesting final confirmation; Tafnit may display a validation message.", flush=True)
    leave_final_confirmation(ui, state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", nargs="?", type=Path, help="Rosh Electroptics Thorlabs PDF quotation; omitted opens a file picker")
    parser.add_argument("--dry-run", action="store_true", help="validate PDF and write review CSV/JSON without touching Tafnit")
    parser.add_argument("--resume", action="store_true", help="resume this PDF's checkpoint after checking the open requisition")
    parser.add_argument("--state-dir", type=Path, help="directory for CSV, checkpoint, and screenshots")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.local.json"),
                        help="private JSON configuration (default: config.local.json beside the script)")
    parser.add_argument("--budget-note", help="override the local config's internal funding note")
    args = parser.parse_args(argv)
    pdf = args.pdf
    if pdf is None:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        selected = filedialog.askopenfilename(title="Select Rosh/Thorlabs quotation", filetypes=[("PDF quotations", "*.pdf")])
        root.destroy()
        if not selected:
            return 0
        pdf = Path(selected)
    ui = None
    try:
        config = load_config(args.config) if args.config.exists() or not args.dry_run else None
        budget_note = args.budget_note if args.budget_note is not None else (config.budget_note if config else "")
        if not args.dry_run and not budget_note.strip():
            raise AutomationError("The funding note cannot be blank.")
        pdf = pdf.resolve(strict=True)
        quote = load_quote(pdf)
        fingerprint = hashlib.sha256(pdf.read_bytes()).hexdigest()
        directory = args.state_dir or pdf.parent / (pdf.stem + "-tafnit")
        directory.mkdir(parents=True, exist_ok=True)
        export_items(quote, directory / "items.csv")
        review = {"quote": quote.number, "date": quote.date, "supplier": "THORLABS INC",
                  "supplier_code": config.supplier_code if config else None, "agent": "Rosh Electroptics",
                  "agent_code": config.agent_code if config else None,
                  "rows": len(quote.items), "units": str(sum(i.quantity for i in quote.items)),
                  "currency": "USD", "pdf_total": str(quote.total), "tafnit_exact_total": str(quote.exact_total),
                  "budget_note": budget_note, "customs_description": CUSTOMS_TEXT,
                  "customs_usage": CUSTOMS_TEXT, "final_confirmation": "user only"}
        (directory / "review.json").write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{quote.number}: {len(quote.items)} rows, {review['units']} units, USD {quote.total:,.2f}")
        print(f"Tafnit unrounded total: USD {quote.exact_total}; review files: {directory}")
        if args.dry_run:
            print("PDF validation passed. No browser or desktop actions performed.")
            return 0
        state = Checkpoint(directory / "state.json", fingerprint, resume=args.resume)
        if state.data["stage"] == "awaiting_user_confirmation":
            raise AutomationError("This run has already handed final confirmation to you. Check the existing request in Tafnit.")
        config_hash = hashlib.sha256(json.dumps(asdict(config), sort_keys=True).encode()).hexdigest()
        if state.data.get("config_sha256", config_hash) != config_hash:
            raise AutomationError("Local configuration changed since this run began. Restore it before resuming.")
        state.update(config_sha256=config_hash)
        print("Keep the original purchase request open in Chrome on display 1." if args.resume
              else f"Keep Tafnit's home screen or a blank purchase request open in Chrome on display 1. The script opens '{PURCHASE_REQUEST_LABEL}' when needed.")
        print("Starting in 5 seconds. Move the mouse to a screen corner to stop; Ctrl+C also stops.")
        time.sleep(5)
        ui = TafnitDesktop(directory, config, allow_open_request=not args.resume)
        run_entry(ui, quote, pdf, state, budget_note)
        print("STOPPED after requesting final confirmation. Inspect Tafnit's confirmation or validation message; no final approval was clicked.")
        return 0
    except (QuoteError, AutomationError, OSError, ValueError, KeyboardInterrupt) as exc:
        if ui is not None:
            ui.screenshot("stopped")
        print(f"Stopped: {exc or 'interrupted by user'}. No final confirmation was clicked.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
