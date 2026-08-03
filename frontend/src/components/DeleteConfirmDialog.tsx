import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";

interface DeleteConfirmDialogProps {
  datasetName: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy: boolean;
}

export function DeleteConfirmDialog({
  datasetName,
  onConfirm,
  onCancel,
  busy,
}: DeleteConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    confirmRef.current?.focus();
  }, []);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") onCancel();
  }

  return (
    <div className="dialog-backdrop" onKeyDown={handleKeyDown}>
      <div
        className="dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-dialog-title"
        aria-describedby="delete-dialog-description"
      >
        <h2 id="delete-dialog-title">Delete dataset</h2>
        <p id="delete-dialog-description">
          Are you sure you want to delete <strong>{datasetName}</strong>? This cannot be undone.
        </p>
        <div className="button-row">
          <button type="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button ref={confirmRef} type="button" onClick={onConfirm} disabled={busy}>
            {busy ? "Deleting…" : "Delete dataset"}
          </button>
        </div>
      </div>
    </div>
  );
}
