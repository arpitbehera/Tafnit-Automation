# General quotation workflow

The reliable generalization is a validated interchange format, not a universal
PDF parser. All processing stays local. Known Rosh/Thorlabs quotations reuse the
existing parser; other PDFs produce text and editable JSON/CSV templates. A
reviewed JSON document (optionally with a separate item CSV) represents any
vendor without claiming that arbitrary document layouts can be parsed safely.

`tafnit.py` orchestrates extraction, review, supplier prompts, configuration,
checkpointing and entry. `quotation.py` owns the interchange format, Decimal
validation and CSV/PDF conversion. `desktop.py` reuses the existing low-level
desktop helpers and implements vendor-independent fields and verification.
`configuration.py` owns institution settings and explicit Tafnit mappings.
The original Rosh workflow remains unchanged.

The operator supplies the registered supplier code, exact name displayed by
Tafnit, optional agent code, and optional supplier website fallback. The resolved supplier name and codes must
match before items are entered. Vendor registration is verified by Tafnit's
lookup, not a separate registry or an invented identifier. Institution settings
and layout mappings live in ignored local configuration.

Amounts are decimal strings, dates are ISO dates, each quotation has one
currency, and each row includes its unit and printed extended amount. Every
row and the net/tax/grand totals must reconcile. Freight must be an explicit
line. Credits, negative lines, order-level discounts and ambiguous price/tax
bases are rejected or explicitly normalized by the operator before entry.

Desktop support is bounded by the observed 12-column Tafnit item form. Currency
codes, request type, purpose, classification, units and total-field mappings
are configured; no domestic codes, VAT rates or foreign exchange rates are
guessed. Nonzero tax requires configured tax and gross readback fields and
must match Tafnit's existing tax calculation. Zero-tax drafts without tax/gross
readback are explicitly marked unverified; opening final confirmation always
requires both mappings. Unmapped units/currencies stop
before browser entry. Changed layouts require adapting and validating the
adapter. The supplied foreign-USD profile is derived from the existing script;
other mappings require local form verification.

Dry-run never initializes desktop automation. Live entry requires a quotation
review and typed confirmation, saves a draft, verifies rows/header/attachments/
totals, then stops. Opening the final research-use dialog is an explicit option;
it records an irreversible handoff in the checkpoint first. There is no final
approval action. Resume checks the PDF and the complete reviewed input/profile/
vendor fingerprint before touching the desktop and verifies existing rows.

The final checkpoint records a handoff attempt, not proof of submission or of
an open dialog. Tafnit may show validation instead. Source descriptions stay
unchanged; entry/readback use the same legacy-safe sign replacements as the
Rosh flow. Catalogued rows retain and verify the reviewed description as well as
the exact part number, because one SKU may identify several configurations.
Read-only description fields fail safely through the inherited input helper.
Item URLs are optional reviewed data, falling back to an explicit
supplier website only when the catalog has no URL. Empty optional website fields
are omitted from canonical data so existing reviewed-data checkpoints still match.

Tests use synthetic data and mocked desktop boundaries. No live requisition is
created during development. Documentation distinguishes offline verification
from live form validation, and explains recovery and support limits.
