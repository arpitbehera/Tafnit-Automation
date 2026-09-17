# Development and tests

Entry points are `RoshElectroptics/rosh_thorlabs_tafnit.py` and
`Generalization/tafnit.py`. Both invocation styles work from the repository root:

```powershell
uv run RoshElectroptics/rosh_thorlabs_tafnit.py --help
uv run python -m RoshElectroptics.rosh_thorlabs_tafnit --help
uv run Generalization/tafnit.py --help
uv run python -m Generalization.tafnit --help
uv run python -m unittest discover -s tests -v
```

Tests use synthetic quotation text and simulated desktop boundaries. They do
not log in, click the browser, or create requisitions. They cover exact decimal
amounts, page continuation, missing/incorrect rows, currencies, item identity,
configuration validation, interruption recovery, and the final handoff.

`tests/test_tafnit_startup.py` covers shared home-screen startup, exact Hebrew
menu matching, the `kalirkosh.py` menu sequence, popup and same-window navigation,
host/display checks,
ambiguous controls, and creation being disabled during resume. Startup clicks
**דרישה לרכש** once; a timeout must never retry that click automatically.

Keep PDF parsing importable without desktop dependencies. GUI dependencies are
installed on Windows only; `--dry-run` and the test suite also work on other
platforms. There is no import-time browser action. Pass an explicit PDF for a
Rosh dry run to avoid its optional file picker; Generalization dry runs always
require an explicit PDF or reviewed-data path.

The image matcher is bundled under `RoshElectroptics/_vendor` so a fresh clone
does not need another checkout. Only its template detection is used. The
application supplies an absolute path to its ten templates, so launch location
does not change where images are found. Optional plotting helpers in the
bundled controller are not part of the workflow and require matplotlib if used.

Shared startup belongs to `TafnitDesktop`; `GeneralDesktop` inherits it. The
four home-menu templates implement **עברית → יזם → עברית → קליטה**, followed
by an exact DOM-label check for **דרישה לרכש**. Keep both CLI constructors
passing `allow_open_request=not args.resume`, and preserve compatibility with
an already-open request. Live home-screen behavior remains unverified.

Preserve the final-confirmation boundary when modifying the workflow:
checkpoint before opening the dialog, never approve it, never issue browser
inputs afterward, and never automatically repeat that final action on resume.
Do not create an actual order merely to exercise tests.

The generalized workflow additionally tests local JSON/CSV normalization,
non-USD currencies, units/tax mappings, exact supplier resolution, input-bound
resume, saved-draft defaults, and no GUI access on dry-run, cancellation or
handoff resume. It does not infer a universal PDF layout or use cloud extraction.
Its desktop adapter reuses low-level helpers while replacing supplier-specific
entry logic. See [the design](../Generalization/DESIGN.md) and
[format documentation](../Generalization/FORMAT.md).

`tests/test_generalization_fixes.py` covers propagation of the fixes found in
live Rosh ordering: legacy-safe descriptions, `(UK)` source notes, required
product websites, exact-case field lookup, missing archive fields after reload,
and post-save corruption blocking the final handoff. Generalization inherits
the corrected `fill`, `select` and `save` helpers directly. Website data remains
local and participates in the resume fingerprint when nonempty.
The same regression suite checks that catalog lookup preserves quoted
configuration details, including different descriptions sharing a supplier SKU.

`tests/test_generalization_catalog.py` covers locked catalog descriptions with
quotation remarks, saved-line identity, post-save remarks loss, and resume after
a row save without duplicate entry. It also exercises the observed USD profile
against synthetic taxable totals and mixed blank/`EACH` unit labels. The tests
remain offline; they do not retry or submit any existing draft.

Use `uv lock` after editing dependencies, then `uv sync --locked`. Keep real
quotation data and local configuration out of fixtures and commit history; see
[privacy guidance](PRIVACY.md).

## Checking documentation changes

Compare each options table with the corresponding `--help` and `main()`:
the Rosh dry run may load its default profile and can open a picker when no
PDF is supplied; Generalization's dry run skips its default profile and rejects
resume/final-handoff flags. Rosh starts live entry without a review prompt and
requests final confirmation automatically; Generalization requires `ENTER`
and defaults to a saved draft.

For an offline smoke check, use the synthetic Generalization example and a
temporary output directory of your choice:

```powershell
uv run Generalization/tafnit.py --data Generalization/quotation.example.json --dry-run --state-dir "$env:TEMP\tafnit-docs-example"
git diff --check
```

Check relative Markdown links, profile examples, template counts and recovery
instructions when changing shared desktop behavior. The implementation record
under `Generalization/` tracks completed work; the two workflow guides are the
operating instructions. Do not use live entry to validate documentation examples.
