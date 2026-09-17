# Rosh/Thorlabs local configuration

This profile is for `RoshElectroptics/rosh_thorlabs_tafnit.py` only.
`Generalization/tafnit.py` uses a [separate schema](../Generalization/CONFIGURATION.md).

Copy `RoshElectroptics/config.example.json` to
`RoshElectroptics/config.local.json`, then fill every value with a JSON string.
The example intentionally contains no institution IDs or personal information.
The local file is ignored by Git. Keep it private, including when reporting bugs.

| Key | Value to use |
| --- | --- |
| `tafnit_host` | Hostname of your Tafnit site, without `https://` or a path |
| `supplier_code` | Your Tafnit supplier code for THORLABS INC |
| `agent_code` | Your Tafnit agent code for Rosh Electroptics |
| `research_group` | Research group ID already selected in your blank request |
| `requester` | Your requester ID |
| `department` | Department ID |
| `building`, `floor`, `room` | Delivery location IDs/values |
| `contact_building`, `contact_floor`, `contact_room` | Contact location IDs/values |
| `budget_note` | Internal note specifying the funding source |

Use the codes shown in the form, not display names. Keep leading zeros by using
strings. The script checks these settings on every run and before the final
handoff. Your contact phone is read from the quotation at runtime.

This workflow uses a funding note and a blank budget-number field. If your
institution requires a budget number or a different approval process, adapt the
workflow before using it.

Live entry stops if the profile is missing, has blank values, or contains
unknown/missing keys. A resumed run also checks that the profile has not changed.
Use `--config "D:\Private\profile.local.json"` to keep the file outside the
repository. A PDF-only dry run does not require a profile, but if the selected
profile exists, it is loaded and must be valid. Unlike Generalization, the Rosh
dry run also loads its default profile when present. Merely passing dry-run
does not check that the values match the live browser.

The profile does not select the home-screen menu. When opening a new request,
startup selects exactly **דרישה לרכש** via **עברית → יזם → עברית → קליטה**
when needed. An already-open request skips navigation, and resume never opens
a new one. The Rosh script then
selects its fixed foreign-purchase type, procurement purpose and USD currency
inside that form. Default research group, requester, department and locations
must already match your profile when the new form opens.

`--budget-note "TEXT"` overrides only the funding note. Supply the same override
again on resume; do not change the profile underneath an interrupted run.

No password, API key, or session cookie belongs in this file. Log in through
Chrome normally before running desktop entry.
