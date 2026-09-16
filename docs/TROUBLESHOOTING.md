# Stopping and recovery

Move the pointer to a screen corner to trigger PyAutoGUI's stop, or press Ctrl+C
in the terminal. A failure can leave saved rows or a draft requisition in Tafnit;
it does not undo them.

Inspect the visible form and the local checkpoint/screenshots, resolve the
reported issue, then keep or reopen **the same requisition** and run with
`--resume`. Resume verifies the PDF hash, profile, saved request number when
available, header, and actual entered rows. A row accepted just before a crash
is recognized from the table and is not entered again.

An unsaved form that has been closed cannot be restored from the checkpoint
alone. Inspect Tafnit for any saved draft before deliberately starting over.

| Problem | Action |
| --- | --- |
| Missing local config | Follow [configuration setup](CONFIGURATION.md). |
| Wrong research group/requester/location | Set the intended defaults in the blank Tafnit form and match the local profile. |
| DevTools did not open separately | Undock DevTools and select Console as described in the workflow guide. |
| Control missing, hidden, or disabled | Inspect the current tab, warning, and form state; avoid moving the browser during entry. |
| Template not found | Confirm 2560×1440, 100% scaling/zoom, display 1, and the expected dialog. Changed UI crops may need updating. |
| Item or price mismatch | Inspect the affected saved row; resume only after correcting it. Catalog lookup can replace values. |
| PDF parse/total failure | Check whether it is a scan, different quotation layout/currency, or an altered/missing page. |
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
