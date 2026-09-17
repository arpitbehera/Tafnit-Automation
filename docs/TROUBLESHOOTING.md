# Stopping and recovery

Move the pointer to a screen corner to trigger PyAutoGUI's stop, or press Ctrl+C
in the terminal. A failure can leave saved rows or a draft requisition in Tafnit;
it does not undo them.

Inspect the visible form and local artifacts before rerunning. The default
artifact directories are `<PDF-stem>-tafnit` for Rosh and
`<PDF-stem>-general-tafnit` for Generalization, beside the PDF. If you supplied
`--state-dir`, inspect that directory instead.

- If `state.json` exists, keep or reopen **the same requisition** and add
  `--resume` to the original command. Repeat the same PDF, profile, output path
  and any reviewed-data/CSV or funding-note arguments. Resume verifies the
  recorded inputs and live request before continuing. A row accepted just before
  a crash is recognized from the table and is not entered again.
- If no checkpoint exists, fix the reported issue and rerun the original
  command without `--resume`. Parsing/configuration failures, unsupported-layout
  templates, dry runs and cancellation of the Generalization review can stop
  before a checkpoint is created. Review files alone are not a checkpoint.

Generalization reuses its saved supplier details on resume but still requires
typing the word `ENTER` after the review. Rosh resumes after its countdown
without that prompt. Neither workflow opens a new request during resume.

An unsaved form that has been closed cannot be restored from the checkpoint
alone. Inspect Tafnit for any saved draft before deliberately starting over.

## Startup failures

Both scripts create their live checkpoint before attempting desktop startup.
An error finding the home menu, opening DevTools or loading the request can
therefore leave `state.json` while its saved request number is still blank.
First check for the form that may already have opened, including another Chrome
window. Reopen that form and use `--resume`; the creation click is never retried.
Only if startup stopped before opening any form should you manually follow
**עברית → יזם → עברית → קליטה → דרישה לרכש**, verify that it is blank and
New, and resume. Do not use a replacement blank form for a run that has already
entered items or saved a request.

| Problem | Action |
| --- | --- |
| Missing or invalid local config | Use the [Rosh profile](CONFIGURATION.md) or [Generalization profile](../Generalization/CONFIGURATION.md) for the matching script. The schemas are different; blank examples cannot run live. |
| Desktop entry needs Windows Python | Run from Windows PowerShell with the Windows environment. `uv run python -c "import os; print(os.name)"` must print `nt`. WSL Python is for offline validation. |
| Cannot select a startup window | Activate the intended Tafnit tab on display 1. Keep one request window, or one home window if no request is open. If its title shows only the institution name, use a single Chrome window. |
| Home-screen menu template or exact option missing/ambiguous | Check display/zoom and the menu state. Follow the startup recovery steps above; similar menu names are not selected. |
| New request did not open | Check Chrome popup blocking and any Tafnit message. Inspect for an already-open request before opening one manually; `--resume` requires the original form and never retries creation. |
| Wrong research group/requester/location | Set the intended defaults in the blank Tafnit form and match the local profile. |
| DevTools did not open separately | Undock DevTools and select Console as described in [browser setup](../RoshElectroptics/ROSH_THORLAB_TAFNIT.md#browser-setup). |
| Control missing, hidden, or disabled | Inspect the current tab, warning, and form state; avoid moving the browser during entry. |
| Template not found | Confirm 2560×1440, 100% scaling/zoom, display 1, and the expected dialog. Changed UI crops may need updating. |
| Item or price mismatch | Inspect the affected saved row; resume only after correcting it. Catalog lookup can replace values. |
| PDF parse/total failure | Check whether it is a scan, different quotation layout/currency, or an altered/missing page. |
| Generalization exits `2` and writes templates | This is the unsupported-layout review path. Fill reviewed JSON/CSV, then run with `--data` and `--dry-run`; see [the guide](../Generalization/README.md#try-local-validation). No request was opened. |
| No checkpoint exists on resume | Use the original command without `--resume` only after checking that the previous attempt stopped before entry; also verify `--state-dir` and the PDF path. |
| Checkpoint already exists | Inspect the existing request and resume that run. Do not delete its checkpoint or change the output directory merely to repeat entry. |
| Generalization is waiting after the review | Type the word `ENTER` and then press the Enter key. Pressing Enter alone cancels. |
| Source input collides with generated output | Copy the reviewed JSON/CSV outside the output paths, preserving the original `--state-dir` on resume. |
| Hidden document-description validation | The script populates the archive description before saving. Inspect the attachment dialog if validation persists. |
| Existing customs declaration | Do not regenerate blindly: generating adds another attachment. See below. |

## Customs attachments

The script reuses one declaration previously verified by the same run. This
assumes the attachment has not been replaced or edited since verification.
Unexpected or duplicate declarations cause a stop.

To remove a superseded declaration manually, hover its attachment row and click
the red X at the left edge. Check the remaining attachment carefully before
resuming. The script never deletes attachments automatically.

## Final confirmation

The Rosh script requests final confirmation automatically after verification.
Generalization normally stops at `Saved draft <number>`; only
`--open-final-confirmation` requests the dialog. A saved generalized draft can
be resumed with that flag if its original profile already has all total mappings.
Neither script confirms the dialog for you.

Once the handoff is recorded, the script refuses to repeat submission—even if
the final click failed or the run was interrupted. Inspect the existing request
and finish the final confirmation manually. Do not delete the checkpoint to
bypass this protection on an already submitted order.

## Known verification limits

The workflow was derived from an observed completed requisition. PDF parsing,
financial checks, resume behavior, and the confirmation boundary have offline
regression tests. Browser reading, filling, selection, and clicking were tested
on a local form. The extracted public version has not been exercised by creating
another live order; a changed Tafnit form can require manual intervention.
Home-screen startup is covered by simulated window/DOM tests; it has not yet
been verified against a live logged-in home screen.
