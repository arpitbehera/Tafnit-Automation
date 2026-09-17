# Reviewed quotation JSON and CSV

Start from [quotation.example.json](quotation.example.json), a synthetic example,
or the blank templates emitted for unknown PDFs. JSON must contain the documented
required keys and may include the documented optional item `website`.
Unknown/duplicate keys are errors, so a misspelled tax or
shipping field cannot be silently ignored.

| Key | Meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `vendor_name` | Invoice recipient/supplier; the company to which the purchase order must be issued, which may differ from the quotation's agent |
| `number` | Quotation identifier, as printed |
| `date` | Unambiguous ISO date `YYYY-MM-DD`; entered in remarks as `DD/MM/YYYY` |
| `currency` | One uppercase three-letter code, e.g. `USD`, `EUR`, `ILS` |
| `currency_decimals` | Printed monetary precision, integer `0`–`3`; normally `2` for those currencies |
| `payment_terms` | Text from the quote; `""` if absent |
| `notes` | Reviewed delivery/packaging/weight/normalization notes; `""` if absent |
| `net_total` | Sum of printed item amounts, excluding tax |
| `tax_total` | Explicit quoted tax amount; `"0"` only when there is no quoted tax |
| `total` | `net_total + tax_total` |
| `items` | Nonempty item array, or `[]` when supplying `--items-csv` |

All monetary values, quantities and percentages must be **JSON strings** with a
period decimal separator, no thousands separators, signs or exponent notation:
`"1234.56"`, not `1,234.56`, `"1234,56"` or `1234.56`. This avoids floating-point
rounding and regional number ambiguity. Normalize the source's number format
deliberately; the parser does not infer whether a comma is a decimal separator.

Each item contains these required keys:

| Key | Meaning |
| --- | --- |
| `part_number` | Supplier SKU used for Tafnit catalog lookup; `""` for an item without a SKU |
| `description` | Nonblank item description, including packaging when relevant |
| `quantity` | Positive decimal string; maximum 3 fractional places |
| `unit` | Explicit unit, e.g. `PCS`, `BOX`, `HOUR`; must match a configured unit mapping |
| `unit_price` | **Pre-tax** unit price before the entered discount; normally the original quoted price, with maximum 3 fractional places; reviewed normalization is described below |
| `discount_percent` | Discount applied to the entered unit price, from `"0"` to `"100"`; maximum 2 fractional places |
| `line_total` | Printed pre-tax extended amount after the item discount |

An item may also contain `"website": "https://vendor.example/product"`.
Use the actual product/supplier URL, not a guessed path. It must be a full HTTP
or HTTPS URL without embedded credentials or spaces; omit it or use `""` if
relying on a catalog URL or the supplier fallback entered at the prompt. Tafnit
may require the website for catalogued items too. An existing catalog link is
preserved; a missing link uses the item website before the supplier fallback.
The program stops before row save when no website is available.
Uncatalogued rows always use reviewed item/supplier input, replacing any stale
website left in the form by an earlier item.

The original `description` stays unchanged in JSON/CSV. Entry and table
verification use `≥` → `>=`, `≤` → `<=`, and `Ø` → `dia. ` because these signs
can become `?` during a full Tafnit page save. The review displays both versions
when they differ. The reviewed description is entered and checked for catalogued
items too: a shared supplier SKU does not prove that lengths, connectors or other
configuration details match. A read-only description field stops entry for manual
handling. Other text is not transliterated; corrupted descriptions cause a stop
after saving, before any final handoff.

The validator checks each line using exact Decimal arithmetic:

```text
quantity × unit_price × (1 − discount_percent / 100)
```

It rounds each calculated line using half-up rounding to `currency_decimals`
and compares it with `line_total`. Summed printed lines must equal `net_total`,
and net plus tax must equal `total`. Tafnit row/net readback uses its observed
three-decimal display and entered prices; therefore the exact Tafnit net can
differ from the sum of printed rounded lines. Both values appear in the review.
A configured gross total must match the quotation at its currency precision;
otherwise the script stops for manual reconciliation.

No undocumented tolerance absorbs mismatches. Quotes using a different rounding
convention or more price precision need manual reconciliation or an explicitly
tested adapter extension. There is a 1,000-item limit and no negative amounts.

## CSV alternative

Keep all header/totals keys in JSON and set `items` to `[]`. Use UTF-8 (optional
BOM), commas and this exact header/order, optionally followed by `website`:

```csv
part_number,description,quantity,unit,unit_price,discount_percent,line_total
EX-1,Example sensor,2,PCS,10.01,0,20.02
,Freight,1,PCS,8.00,0,8.00
```

With product URLs, append the optional column:

```csv
part_number,description,quantity,unit,unit_price,discount_percent,line_total,website
EX-1,Example sensor,2,PCS,10.01,0,20.02,https://vendor.example/product
,Freight,1,PCS,8.00,0,8.00,
```

New blank CSV templates include `website`. Existing seven-column CSVs continue
to work. Review exports include the column when at least one item has a URL.

Use ordinary CSV quoting around descriptions containing commas. Retain leading
zeros in SKUs and original decimal precision when editing in a spreadsheet.
Supplying both embedded JSON items and `--items-csv` is rejected. Extra/missing
columns or cells are rejected. `items.review.csv` has the same columns; copy it
to an input location outside the output directory if using it for a later run.

## Cases that need deliberate handling

- **Freight/packing:** include each quoted charge as a separate positive item,
  with an appropriate description/unit and net amount. Do not hide it in notes.
- **Tax:** item prices must exclude tax. Do not paste tax-inclusive unit prices
  and add tax again. The script checks the quoted tax amount against configured
  live fields; it does not determine tax eligibility or change Tafnit's rates.
- **Quote-level discounts:** no automatic distribution. Supply a reviewed
  per-line representation only if it faithfully represents the quotation and
  Tafnit's permitted entry; otherwise enter/reconcile manually.
- **Reviewed net prices:** if entry uses already-discounted amounts, set the
  entered discount to `"0"` to avoid applying it twice. Preserve the original
  prices, source currency, discount and normalization basis in `notes` and a
  private source record. For a quantity-one row, its printed pre-tax amount in
  the chosen currency can serve as that net unit price. For other quantities,
  division and rounding must still reconcile exactly at the supported precision.
  This is deliberate reviewed input, not an inferred exchange-rate conversion.
- **Approved positive footer adjustments:** an explicitly reviewed positive
  net adjustment can be a separate quantity-one line, with its source label and
  amount in the description, no part number, and zero discount. Keep the quoted
  net, tax and gross totals. Do not call it freight or extra goods. Confirm that
  the configured Tafnit unit and classification fit the adjustment; this adapter
  uses one classification for uncatalogued rows, so a separate classification
  requirement needs manual entry or an adapter extension. Negative adjustments
  remain unsupported. Ambiguous signs or labels need resolution before input.
- **Alternative/optional items:** include only the selected purchase and its
  corresponding reviewed totals; do not combine mutually exclusive options.
- **Units/packages:** buying `2 BOX` is not the same as `2 PCS`. Preserve the
  quantity basis and configure the actual Tafnit unit. A missing mapping stops.
- **Catalog substitutions:** a returned catalog manufacturer's part must match
  the reviewed part number exactly. The reviewed description must also survive
  entry and full-page save; a generic catalog description cannot substitute for
  the quoted configuration, even when the SKU matches. Older drafts saved with
  catalog descriptions may stop on resume and need manual correction.
- **Known Rosh warehouse/source suffixes:** the Rosh adapter removes suffixes
  such as `(DE WH)` and `(UK)` for catalog matching and records the original
  value in `notes`. It derives each Thorlabs product URL from the original SKU
  without its trailing source note and URL-encodes characters such as `/`.
  Other suffixes such as `(LEFT)` remain part of the catalog SKU. Generic
  JSON/CSV imports do not silently strip suffixes or invent product URLs.
- **Mixed currency, credits, special approval routes or unrepresentable data:**
  use an appropriate manual workflow. Do not force them into this schema by
  discarding rows or inventing a currency conversion.

The JSON is a reviewed representation of the PDF, not proof of its contents.
The runtime checkpoint binds the PDF bytes, normalized data, vendor selection
and profile so that a later resume cannot silently switch them.

## Diagnosing an unfamiliar quotation

Exit `2` with blank templates means that the PDF layout has no validated parser;
it does not mean that text extraction failed. Check `extracted.local.txt` against
the PDF visually. Plain extracted text can lose table column alignment, so use
the original document to assign prices, discounts and totals.

Before filling the templates, check that all prices, line amounts and totals
use the same currency. Some quotations print foreign-currency unit prices and
local-currency totals. An exchange rate inferred from rounded totals is not an
approved entry rate, especially when the quote ties billing to a future rate.
This schema cannot represent that conversion or its separate rounding rules.

Also check that printed line amounts sum to the stated net total. A footer
labelled discount or rounding may change that net amount. Do not omit the
adjustment, absorb it into tax, invent a freight item, or change unit prices
merely to pass validation. Obtain confirmed entry values and a supported
representation, or reconcile the draft manually. Successfully validating
different synthetic data does not make the original quotation's dry-run pass.
