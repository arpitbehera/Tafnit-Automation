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

If a secret is accidentally published, removing it in a later commit does not
remove it from history. Revoke exposed credentials and arrange history cleanup
before sharing the repository further.
