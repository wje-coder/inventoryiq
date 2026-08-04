import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { AnalyticsApiError, getAnomalies, type AnomalyFinding } from "../api/analytics";
import { listDatasets, type Dataset } from "../api/datasets";
import { NavBar } from "../components/NavBar";

export function AnomaliesPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyFinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDatasets() {
      const result = await listDatasets();
      const ready = result.filter((d) => d.status === "ready");
      setDatasets(ready);
      if (ready.length > 0) setSelectedDatasetId((current) => current ?? ready[0].id);
    }
    void loadDatasets();
  }, []);

  const loadAnomalies = useCallback(async () => {
    if (!selectedDatasetId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getAnomalies(selectedDatasetId);
      setAnomalies(result.anomalies);
    } catch (err) {
      setError(err instanceof AnalyticsApiError ? err.message : "Failed to load anomalies.");
    } finally {
      setLoading(false);
    }
  }, [selectedDatasetId]);

  useEffect(() => {
    void loadAnomalies();
  }, [loadAnomalies]);

  return (
    <>
      <NavBar />
      <div className="analytics-page">
        <div className="analytics-page-header">
          <h1>Anomalies</h1>
          <nav aria-label="Analytics sections">
            <Link to="/analytics">Dashboard</Link>
            <Link to="/analytics/data-quality">Data Quality</Link>
          </nav>
        </div>

        <div className="panel">
          <label htmlFor="anomalies-dataset-select">Dataset</label>
          <select
            id="anomalies-dataset-select"
            value={selectedDatasetId ?? ""}
            onChange={(event) => setSelectedDatasetId(event.target.value)}
          >
            <option value="" disabled>
              Select a dataset
            </option>
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.display_name}
              </option>
            ))}
          </select>
        </div>

        {loading && <p>Loading anomalies…</p>}
        {error && (
          <p className="status-error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && (
          <div className="panel">
            <h2>Detected Anomalies</h2>
            {anomalies.length === 0 ? (
              <p className="text-muted">No anomalies detected.</p>
            ) : (
              <table aria-label="Detected anomalies">
                <thead>
                  <tr>
                    <th scope="col">Type</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Entity</th>
                    <th scope="col">Metric</th>
                    <th scope="col">Value</th>
                    <th scope="col">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {anomalies.map((anomaly, index) => (
                    <tr key={index}>
                      <td>{anomaly.anomaly_type}</td>
                      <td>
                        <span className={`status-badge ${anomaly.severity}`}>
                          {anomaly.severity}
                        </span>
                      </td>
                      <td>{anomaly.entity}</td>
                      <td>{anomaly.metric}</td>
                      <td>{anomaly.value.toLocaleString()}</td>
                      <td>{anomaly.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </>
  );
}
