# Development and tests

The entry point is `RoshElectroptics/rosh_thorlabs_tafnit.py`. Both invocation
styles work from the repository root:

```powershell
uv run RoshElectroptics/rosh_thorlabs_tafnit.py --help
uv run python -m RoshElectroptics.rosh_thorlabs_tafnit --help
uv run python -m unittest discover -s tests -v
```

Tests use synthetic quotation text and simulated desktop boundaries. They do
not log in, click the browser, or create requisitions. They cover exact decimal
amounts, page continuation, missing/incorrect rows, currencies, item identity,
configuration validation, interruption recovery, and the final handoff.

Keep PDF parsing importable without desktop dependencies. GUI dependencies are
installed on Windows only; `--dry-run` and the test suite also work on other
platforms. There is no import-time browser action.

The image matcher is bundled under `RoshElectroptics/_vendor` so a fresh clone
does not need another checkout. Only its template detection is used. The
application supplies an absolute path to its six templates, so launch location
does not change where images are found. Optional plotting helpers in the
bundled controller are not part of the workflow and require matplotlib if used.

Preserve the final-confirmation boundary when modifying the workflow:
checkpoint before opening the dialog, never approve it, never issue browser
inputs afterward, and never automatically repeat that final action on resume.
Do not create an actual order merely to exercise tests.

Use `uv lock` after editing dependencies, then `uv sync --locked`. Keep real
quotation data and local configuration out of fixtures and commit history; see
[privacy guidance](PRIVACY.md).
