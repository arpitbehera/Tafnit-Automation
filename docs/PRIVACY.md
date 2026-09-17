# Keeping private data out of Git

The public repository contains code, blank configuration, synthetic tests, and
six generic UI crops. It does not include quotation PDFs, real order exports,
personal funding notes, phone numbers, institution IDs, or browser sessions.

`config.local.json` and other `*.local.json` files are ignored. PDF/CSV/Excel
documents, generated order directories, checkpoints, review files, logs,
screenshots, credentials, and environment folders are also ignored. Only the
six generic template PNGs are included as images.

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

The script operates your existing browser login; it does not need credentials
in files. DOM reads use the local Chrome Console. Normal browser requests to
your configured Tafnit site still occur when fields are entered and saved.

The generalized workflow also keeps extraction local. Store its reviewed inputs
as `*.local.json`; CSVs and default `*-general-tafnit` output directories are
ignored. Generated text contains quotation details and is named `*.local.txt`.
There is no AI/cloud OCR fallback. Custom output directories should be outside
the repository. No supplier registry credentials are stored: supplier codes and
names are entered interactively and retained in the private run checkpoint.

If a secret is accidentally published, removing it in a later commit does not
remove it from history. Revoke exposed credentials and arrange history cleanup
before sharing the repository further.
