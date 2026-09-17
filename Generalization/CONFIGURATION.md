# Generalized form configuration

Copy [config.example.json](config.example.json) to `config.local.json`, fill it
locally, and keep it private. All institution and code values are strings to
preserve leading zeros. This schema is separate from the Rosh profile.

| Setting | Value |
| --- | --- |
| `tafnit_host` | Your logged-in Tafnit hostname, without scheme/path |
| `header.MEHKAR`, `IZAM`, `MHLK` | Research group, requester, department codes already selected on the blank request |
| `header.Building`, `Floor`, `Room` | Delivery defaults |
| `header.CBuilding`, `CFloor`, `CRoom` | Contact location defaults |
| `budget_note` | Internal funding note; the budget-number field must be blank |
| `request_type_code` | Verified value of Tafnit's `SUGD` select |
| `purpose_code` | Verified value of Tafnit's `MHTD` select |
| `classification.category_code` | Appropriate `KitlugFLD0A` option for uncatalogued rows |
| `classification.subcategory_code` | Appropriate `KitlugFLD0B` option for uncatalogued rows |
| `customs.required` | Boolean `true`/`false` for this specific workflow |
| `customs.description`, `customs.usage` | Actual goods description and intended use; mandatory if customs is required |

The example's request type `4`, purpose `1`, currency code `1`/USD and
total fields come from the observed foreign-purchase flow. They are not
universal Weizmann procurement rules. The legacy classification `1`/`7` means
scientific equipment/laboratory instruments in that observed form; use it only
when correct for the items. Classification is intentionally blank in this
example. A mixed-classification uncatalogued order needs manual handling or an
adapter extension. Do not apply the original optics customs sentence to other
goods without reviewing it.

## Currency and totals

Each quotation currency needs a `currencies` entry with these exact keys:

```json
"USD": {
  "code": "1",
  "row_labels": ["$ ארהב", "בהרא $", "USD"],
  "net_total_field": "BrutoaDollar",
  "tax_total_field": "MamDollar",
  "gross_total_field": "NetoDollar"
}
```

`code` is written to header `KM` and line `Coin`. `row_labels` lists exact
display strings for that currency in item-table column 5; matching ignores
case and repeated whitespace. A dollar symbol alone is ambiguous, so configure
only the labels verified on your form for the selected code. The observed
legacy item table exposes the USD label as `בהרא $` in its DOM text; the header
shows `$ ארהב`. These are explicit aliases, not a general text-reversal rule.

The total fields must be DOM IDs whose `.value` contains numeric amounts in
**the quotation currency**, not converted amounts or formatted HTML. `net`
means the pre-tax sum from entered item prices after entered discounts,
displayed to three decimals.
`tax` is the actual tax amount, and `gross` is the amount payable including tax.
On the inspected USD form, `BrutoaDollar` is the subtotal after discounts,
`MamDollar` is the VAT amount, and `NetoDollar` is the total **including VAT**.
Despite its name, `NetoDollar` is not the pre-tax subtotal. Budget-reservation
fields, which may include an additional reserve, are not supplier totals.
Do not reuse these USD fields for another currency without verifying semantics.

The example now includes all three observed USD total fields. Existing local
profiles are not rewritten: for new requests, replace the old net mapping to
`NetoDollar` with `BrutoaDollar` and add tax/gross mappings as above after checking
your form. Do not change an active run's profile and attempt to resume it;
its checkpoint binds the original profile. Finish that draft manually.

A custom profile may leave tax/gross mappings blank for a zero-tax quotation;
those totals are then **UNVERIFIED** and require manual inspection. Nonzero tax
or `--open-final-confirmation` requires both mappings before entry. Tafnit's
existing tax calculation must match the quotation; the script does not set a
VAT rate, tax exemption or exchange rate.

## Units

`unit_field` identifies the editable item unit control. For every allowed
quotation `unit`, map its code and exact item-table unit labels:

```json
"unit_field": "",
"units": {
  "PCS": {"code": "", "row_labels": ["", "EACH"]}
}
```

The supplied mapping represents the legacy form's observed default pieces unit:
uncatalogued rows have a blank unit cell and catalogued pieces display `EACH`.
It does not authorize treating boxes or packs as single pieces; verify the
catalog's packaging and quantity basis against the quotation. With no unit control
mapped, only one default unit is permitted, and its code must be blank. To
support BOX, HOUR or other units, inspect the real unit control, set its DOM ID
in `unit_field`, and add each verified code/label. Dropdowns use their option
value; text controls use the mapped code. Do not guess the unit control ID.

## Inspecting a new form mapping

Do this manually on the correct request type before running automation. In
Chrome DevTools, the following expression reads known dropdown choices and
current values without submitting anything:

```javascript
Object.fromEntries(
  ["SUGD", "MHTD", "KM", "Coin", "KitlugFLD0A", "KitlugFLD0B"].map(id => {
    const e = document.getElementById(id);
    return [id, !e ? null : e.options
      ? [...e.options].map(o => ({value: o.value, text: o.text}))
      : {value: e.value}];
  })
)
```

Use the Elements inspector to identify the actual unit and total controls and
compare their values with the form's visible labels. A missing control, a
different 12-column item table, special tax treatment or a different purchase
process needs an adapter change; adding a plausible ID is not validation.
Validate a synthetic or carefully inspected draft before relying on a new
profile. The example's USD totals and table labels were checked on an assisted
live foreign-purchase draft; other forms and currencies need their own checks.

Supplier details do not belong in this reusable institution profile: the CLI
asks for them for each new quotation and retains them in its private checkpoint
for resume. This includes the optional supplier website fallback, used only
when the catalog and the reviewed item have no website. Item URLs can be supplied
in JSON or an optional final CSV `website` column; see [FORMAT.md](FORMAT.md).
There is no new required profile setting for websites.

Header defaults must already match the blank form; the script stops
instead of silently changing the requester, department or delivery destination.
