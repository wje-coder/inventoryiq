import { useEffect, useState } from "react";

import {
  BUSINESS_FIELDS,
  BUSINESS_FIELD_LABELS,
  DatasetApiError,
  updateDatasetColumnMappings,
  type BusinessField,
  type DatasetColumn,
} from "../api/datasets";

interface ColumnMappingEditorProps {
  datasetId: string;
  columns: DatasetColumn[];
  availableAnalyses: string[];
  onSaved: (columns: DatasetColumn[], availableAnalyses: string[]) => void;
}

export function ColumnMappingEditor({
  datasetId,
  columns,
  availableAnalyses,
  onSaved,
}: ColumnMappingEditorProps) {
  const [mappings, setMappings] = useState<Record<string, BusinessField | "">>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Re-sync the local draft whenever the columns we were given change -
  // this covers both a successful save (parent refreshes `columns` with
  // the new mapping) and switching to a different dataset entirely. Note
  // this deliberately does NOT clear `saved`: a successful save is what
  // causes `columns` to change in the first place, and resetting `saved`
  // here would immediately hide the "Saved." confirmation right after it
  // appears. `saved` is cleared explicitly instead: in handleChange (the
  // user edited something new) and below, keyed on datasetId, so it's
  // still reset when the user switches to viewing a different dataset.
  useEffect(() => {
    const next: Record<string, BusinessField | ""> = {};
    for (const column of columns) {
      next[column.id] = column.mapped_business_field ?? "";
    }
    setMappings(next);
  }, [columns]);

  useEffect(() => {
    setSaved(false);
  }, [datasetId]);

  function handleChange(columnId: string, value: string) {
    setMappings((prev) => ({ ...prev, [columnId]: value as BusinessField | "" }));
    setSaved(false);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const payload = columns.map((column) => ({
        column_id: column.id,
        mapped_business_field: mappings[column.id] ? (mappings[column.id] as BusinessField) : null,
      }));
      const result = await updateDatasetColumnMappings(datasetId, payload);
      onSaved(result.columns, result.available_analyses);
      setSaved(true);
    } catch (err) {
      setError(err instanceof DatasetApiError ? err.message : "Failed to save column mapping.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h3>Column mapping</h3>
      <table className="dataset-table mapping-table" aria-label="Column mapping">
        <thead>
          <tr>
            <th scope="col">Source column</th>
            <th scope="col">Inferred type</th>
            <th scope="col">Sample values</th>
            <th scope="col">Business field</th>
          </tr>
        </thead>
        <tbody>
          {columns.map((column) => {
            const selectId = `mapping-${column.id}`;
            return (
              <tr key={column.id}>
                <td>{column.source_name}</td>
                <td>{column.inferred_type}</td>
                <td className="text-muted">{column.sample_values.join(", ")}</td>
                <td>
                  <label htmlFor={selectId} className="visually-hidden">
                    Business field for {column.source_name}
                  </label>
                  <select
                    id={selectId}
                    value={mappings[column.id] ?? ""}
                    onChange={(event) => handleChange(column.id, event.target.value)}
                  >
                    <option value="">Not mapped</option>
                    {BUSINESS_FIELDS.map((field) => (
                      <option key={field} value={field}>
                        {BUSINESS_FIELD_LABELS[field]}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="button-row" style={{ marginTop: "0.75rem" }}>
        <button type="button" onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save column mapping"}
        </button>
        {saved && (
          <span className="status-ok" role="status">
            Saved.
          </span>
        )}
      </div>

      {error && (
        <p className="status-error" role="alert">
          {error}
        </p>
      )}

      <div style={{ marginTop: "0.75rem" }}>
        <strong>Available analyses:</strong>{" "}
        {availableAnalyses.length > 0 ? (
          <span>{availableAnalyses.join(", ")}</span>
        ) : (
          <span className="text-muted">
            Map columns to business fields to unlock analyses.
          </span>
        )}
      </div>
    </div>
  );
}
