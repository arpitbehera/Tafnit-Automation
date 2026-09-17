# Keeping private data out of Git

The public repository contains code, configuration templates with blank personal
values, synthetic quotations/tests, and ten generic UI crops. It does not include
quotation PDFs, real order exports,
personal funding notes, phone numbers, institution IDs, or browser sessions.

`config.local.json` and other `*.local.json` files are ignored. PDF/CSV/Excel
documents, generated order directories, checkpoints, review files, logs,
screenshots, credentials, and environment folders are also ignored. Only the
ten generic template PNGs are included as images.

Ignore rules are a precaution, not a redaction tool: an already tracked file
remains tracked, and `git add -f` can override the rules. Before publishing changes:

```powershell
git status --short
git diff --cached --stat
git diff --cached
git ls-files
git check-ignore RoshElectroptics/config.local.json
```

Review every added image visually. Use invented quotations in tests, and remove
personal values from exception output or screenshots before sharing an issue.
Keep real PDFs and generated artifacts outside the repository when possible.

Both scripts operate your existing browser login; they do not need credentials
in files or a separate `kalirkosh.py` installation. DOM reads use the local
Chrome Console and clipboard. Normal browser requests to your configured
Tafnit site still occur when menus are opened, fields entered and documents
uploaded or saved. Automation uses the clipboard for field entry and readback;
do not rely on it retaining its previous contents.

The generalized workflow also keeps extraction local. Store its reviewed inputs
as `*.local.json`; CSVs and default `*-general-tafnit` output directories are
ignored. Generated text contains quotation details and is named `*.local.txt`.
There is no AI/cloud OCR fallback. Custom output directories should be outside
the repository. No supplier registry credentials are stored: supplier codes and
names are entered interactively and retained in the private run checkpoint.

If a secret is accidentally published, removing it in a later commit does not
remove it from history. Revoke exposed credentials and arrange history cleanup
before sharing the repository further.
