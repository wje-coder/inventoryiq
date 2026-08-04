import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { AnalyticsApiError, getDataQuality, type DataQualityReport } from "../api/analytics";
import { listDatasets, type Dataset } from "../api/datasets";
import { NavBar } from "../components/NavBar";

export function DataQualityPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [report, setReport] = useState<DataQualityReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsRun, setNeedsRun] = useState(false);

  useEffect(() => {
    async function loadDatasets() {
      const result = await listDatasets();
      const ready = result.filter((d) => d.status === "ready");
      setDatasets(ready);
      if (ready.length > 0) setSelectedDatasetId((current) => current ?? ready[0].id);
    }
    void loadDatasets();
  }, []);

  const loadReport = useCallback(async () => {
    if (!selectedDatasetId) return;
    setLoading(true);
    setError(null);
    setNeedsRun(false);
    try {
      const result = await getDataQuality(selectedDatasetId);
      setReport(result);
    } catch (err) {
      if (err instanceof AnalyticsApiError && err.code === "ANALYTICS_NOT_RUN") {
        setReport(null);
        setNeedsRun(true);
      } else {
        setError(err instanceof AnalyticsApiError ? err.message : "Failed to load data quality.");
      }
    } finally {
      setLoading(false);
    }
  }, [selectedDatasetId]);

  useEffect(() => {
    void loadReport();
  }, [loadReport]);

  return (
    <>
      <NavBar />
      <div className="analytics-page">
        <div className="analytics-page-header">
          <h1>Data Quality</h1>
          <nav aria-label="Analytics sections">
            <Link to="/analytics">Dashboard</Link>
            <Link to="/analytics/anomalies">Anomalies</Link>
          </nav>
        </div>

        <div className="panel">
          <label htmlFor="quality-dataset-select">Dataset</label>
          <select
            id="quality-dataset-select"
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

        {loading && <p>Loading data quality report…</p>}
        {error && (
          <p className="status-error" role="alert">
            {error}
          </p>
        )}
        {needsRun && !loading && (
          <p className="text-muted">
            No analytics have been computed for this dataset yet. Run analytics from the Dashboard
            page first.
          </p>
        )}

        {report && !loading && (
          <>
            <div className="kpi-grid">
              <div className="kpi-card" role="group" aria-label="Overall Data Quality Score">
                <span className="kpi-card-label">Overall Score</span>
                <span className="kpi-card-value">{report.overall_score.toFixed(1)}</span>
              </div>
              <div className="kpi-card" role="group" aria-label="Completeness Score">
                <span className="kpi-card-label">Completeness</span>
                <span className="kpi-card-value">{report.completeness_score.toFixed(1)}</span>
              </div>
              <div className="kpi-card" role="group" aria-label="Validity Score">
                <span className="kpi-card-label">Validity</span>
                <span className="kpi-card-value">{report.validity_score.toFixed(1)}</span>
              </div>
              <div className="kpi-card" role="group" aria-label="Consistency Score">
                <span className="kpi-card-label">Consistency</span>
                <span className="kpi-card-value">{report.consistency_score.toFixed(1)}</span>
              </div>
              <div className="kpi-card" role="group" aria-label="Uniqueness Score">
                <span className="kpi-card-label">Uniqueness</span>
                <span className="kpi-card-value">{report.uniqueness_score.toFixed(1)}</span>
              </div>
            </div>

            <div className="panel">
              <h2>Findings</h2>
              {report.findings.length === 0 ? (
                <p className="text-muted">No data-quality issues detected.</p>
              ) : (
                <table aria-label="Data quality findings">
                  <thead>
                    <tr>
                      <th scope="col">Severity</th>
                      <th scope="col">Category</th>
                      <th scope="col">Description</th>
                      <th scope="col">Recommendation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.findings.map((finding, index) => (
                      <tr key={index}>
                        <td>
                          <span className={`status-badge ${finding.severity}`}>
                            {finding.severity}
                          </span>
                        </td>
                        <td>{finding.category}</td>
                        <td>{finding.description}</td>
                        <td>{finding.recommendation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
