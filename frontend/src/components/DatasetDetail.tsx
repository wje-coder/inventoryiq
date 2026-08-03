import { useCallback, useEffect, useId, useState } from "react";
import type { FormEvent } from "react";

import {
  DatasetApiError,
  deleteDataset,
  getDatasetColumns,
  getDatasetPreview,
  revalidateDataset,
  updateDatasetDisplayName,
  type Dataset,
  type DatasetColumn,
  type DatasetPreview,
} from "../api/datasets";
import { ColumnMappingEditor } from "./ColumnMappingEditor";
import { DeleteConfirmDialog } from "./DeleteConfirmDialog";

interface DatasetDetailProps {
  dataset: Dataset;
  onDatasetUpdated: (dataset: Dataset) => void;
  onDatasetDeleted: (id: string) => void;
}

export function DatasetDetail({ dataset, onDatasetUpdated, onDatasetDeleted }: DatasetDetailProps) {
  const nameInputId = useId();

  const [columns, setColumns] = useState<DatasetColumn[]>([]);
  const [availableAnalyses, setAvailableAnalyses] = useState<string[]>([]);
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [nameDraft, setNameDraft] = useState(dataset.display_name);
  const [savingName, setSavingName] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  const [revalidating, setRevalidating] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [columnsResponse, previewResponse] = await Promise.all([
        getDatasetColumns(dataset.id),
        dataset.status === "ready" ? getDatasetPreview(dataset.id) : Promise.resolve(null),
      ]);
      setColumns(columnsResponse.columns);
      setAvailableAnalyses(columnsResponse.available_analyses);
      setPreview(previewResponse);
    } catch (err) {
      setLoadError(err instanceof DatasetApiError ? err.message : "Failed to load dataset.");
    } finally {
      setLoading(false);
    }
  }, [dataset.id, dataset.status]);

  useEffect(() => {
    setNameDraft(dataset.display_name);
    void load();
  }, [dataset.id, dataset.status, load]);

  async function handleSaveName(event: FormEvent) {
    event.preventDefault();
    setSavingName(true);
    setNameError(null);
    try {
      const updated = await updateDatasetDisplayName(dataset.id, nameDraft);
      onDatasetUpdated(updated);
    } catch (err) {
      setNameError(err instanceof DatasetApiError ? err.message : "Failed to rename dataset.");
    } finally {
      setSavingName(false);
    }
  }

  async function handleRevalidate() {
    setRevalidating(true);
    try {
      const updated = await revalidateDataset(dataset.id);
      onDatasetUpdated(updated);
    } catch (err) {
      setLoadError(err instanceof DatasetApiError ? err.message : "Failed to re-validate dataset.");
    } finally {
      setRevalidating(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteDataset(dataset.id);
      onDatasetDeleted(dataset.id);
    } catch (err) {
      setDeleteError(err instanceof DatasetApiError ? err.message : "Failed to delete dataset.");
      setDeleting(false);
    }
  }

  return (
    <div className="panel">
      <h2>{dataset.display_name}</h2>

      <dl>
        <div>
          <dt>Status</dt>
          <dd>
            <span className={`status-badge ${dataset.status}`}>{dataset.status}</span>
          </dd>
        </div>
        <div>
          <dt>Original filename</dt>
          <dd>{dataset.original_filename}</dd>
        </div>
        <div>
          <dt>Rows / columns</dt>
          <dd>
            {dataset.row_count ?? "—"} / {dataset.column_count ?? "—"}
          </dd>
        </div>
      </dl>

      {dataset.error_message && (
        <p className="status-error" role="alert">
          {dataset.error_message}
        </p>
      )}

      <form onSubmit={handleSaveName} className="field-row">
        <label htmlFor={nameInputId}>Display name</label>
        <div className="button-row">
          <input
            id={nameInputId}
            type="text"
            value={nameDraft}
            onChange={(event) => setNameDraft(event.target.value)}
            required
          />
          <button type="submit" disabled={savingName || nameDraft.trim() === ""}>
            {savingName ? "Saving…" : "Save name"}
          </button>
        </div>
        {nameError && (
          <p className="status-error" role="alert">
            {nameError}
          </p>
        )}
      </form>

      <div className="button-row">
        <button type="button" onClick={handleRevalidate} disabled={revalidating}>
          {revalidating ? "Re-validating…" : "Re-validate"}
        </button>
        <button type="button" onClick={() => setConfirmingDelete(true)}>
          Delete dataset
        </button>
      </div>
      {deleteError && (
        <p className="status-error" role="alert">
          {deleteError}
        </p>
      )}

      {loading && <p>Loading dataset details…</p>}
      {loadError && (
        <p className="status-error" role="alert">
          {loadError}
        </p>
      )}

      {!loading && !loadError && columns.length > 0 && (
        <ColumnMappingEditor
          datasetId={dataset.id}
          columns={columns}
          availableAnalyses={availableAnalyses}
          onSaved={(updatedColumns, analyses) => {
            setColumns(updatedColumns);
            setAvailableAnalyses(analyses);
          }}
        />
      )}

      {!loading && !loadError && preview && (
        <div>
          <h3>Preview ({preview.returned_row_count} of {preview.total_row_count ?? "?"} rows)</h3>
          <div style={{ overflowX: "auto" }}>
            <table className="dataset-table" aria-label="Dataset preview">
              <thead>
                <tr>
                  {preview.columns.map((column) => (
                    <th scope="col" key={column}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {preview.columns.map((column) => (
                      <td key={column}>{String(row[column] ?? "")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && !loadError && dataset.status !== "ready" && (
        <p className="text-muted">
          A preview will be available once the dataset finishes validating.
        </p>
      )}

      {confirmingDelete && (
        <DeleteConfirmDialog
          datasetName={dataset.display_name}
          busy={deleting}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={handleDelete}
        />
      )}
    </div>
  );
}
