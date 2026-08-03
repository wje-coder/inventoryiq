import type { Dataset } from "../api/datasets";

interface DatasetListProps {
  datasets: Dataset[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

export function DatasetList({ datasets, selectedId, onSelect, loading, error }: DatasetListProps) {
  return (
    <div className="panel">
      <h2>Your datasets</h2>

      {loading && <p>Loading datasets…</p>}
      {error && (
        <p className="status-error" role="alert">
          {error}
        </p>
      )}

      {!loading && !error && datasets.length === 0 && (
        <p className="text-muted">No datasets uploaded yet.</p>
      )}

      {!loading && !error && datasets.length > 0 && (
        <table className="dataset-table" aria-label="Uploaded datasets">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Status</th>
              <th scope="col">Rows</th>
              <th scope="col">Columns</th>
              <th scope="col">Size</th>
              <th scope="col">Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((dataset) => (
              <tr
                key={dataset.id}
                className={dataset.id === selectedId ? "dataset-row selected" : "dataset-row"}
                onClick={() => onSelect(dataset.id)}
                tabIndex={0}
                role="button"
                aria-pressed={dataset.id === selectedId}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(dataset.id);
                  }
                }}
              >
                <td>{dataset.display_name}</td>
                <td>
                  <span className={`status-badge ${dataset.status}`}>{dataset.status}</span>
                </td>
                <td>{dataset.row_count ?? "—"}</td>
                <td>{dataset.column_count ?? "—"}</td>
                <td>{formatBytes(dataset.file_size_bytes)}</td>
                <td>{new Date(dataset.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
