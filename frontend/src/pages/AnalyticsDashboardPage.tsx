import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  AnalyticsApiError,
  getAnalyticsSummary,
  getCategories,
  getProducts,
  getRegions,
  getSuppliers,
  getTrends,
  runAnalytics,
  type AnalyticsFilters as AnalyticsFiltersParams,
  type AnalyticsSummary,
  type CategoriesResponse,
  type ProductsResponse,
  type RegionsResponse,
  type SuppliersResponse,
  type TrendsResponse,
} from "../api/analytics";
import { DatasetApiError, listDatasets, type Dataset } from "../api/datasets";
import {
  AnalyticsFilters,
  EMPTY_ANALYTICS_FILTERS,
  type AnalyticsFilterState,
} from "../components/AnalyticsFilters";
import { BarChartCard } from "../components/BarChartCard";
import { KPICard } from "../components/KPICard";
import { LineChartCard } from "../components/LineChartCard";
import { NavBar } from "../components/NavBar";
import { ProductRankingTable } from "../components/ProductRankingTable";
import { KPI_LABELS } from "../api/analytics";

function toApiFilters(filters: AnalyticsFilterState): AnalyticsFiltersParams {
  return {
    dateFrom: filters.dateFrom || undefined,
    dateTo: filters.dateTo || undefined,
    category: filters.category || undefined,
    supplier: filters.supplier || undefined,
    region: filters.region || undefined,
    channel: filters.channel || undefined,
  };
}

export function AnalyticsDashboardPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [filters, setFilters] = useState<AnalyticsFilterState>(EMPTY_ANALYTICS_FILTERS);

  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [trends, setTrends] = useState<TrendsResponse | null>(null);
  const [products, setProducts] = useState<ProductsResponse | null>(null);
  const [categories, setCategories] = useState<CategoriesResponse | null>(null);
  const [suppliers, setSuppliers] = useState<SuppliersResponse | null>(null);
  const [regions, setRegions] = useState<RegionsResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsRun, setNeedsRun] = useState(false);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    async function loadDatasets() {
      try {
        const result = await listDatasets();
        setDatasets(result.filter((d) => d.status === "ready"));
        if (result.length > 0) setSelectedDatasetId((current) => current ?? result[0].id);
      } catch {
        // Handled below by the empty-datasets state.
      }
    }
    void loadDatasets();
  }, []);

  const loadAnalytics = useCallback(async () => {
    if (!selectedDatasetId) return;
    setLoading(true);
    setError(null);
    setNeedsRun(false);

    const apiFilters = toApiFilters(filters);

    try {
      const [trendsResult, productsResult, categoriesResult, suppliersResult, regionsResult] =
        await Promise.all([
          getTrends(selectedDatasetId, "monthly", apiFilters),
          getProducts(selectedDatasetId, apiFilters),
          getCategories(selectedDatasetId, apiFilters),
          getSuppliers(selectedDatasetId, apiFilters),
          getRegions(selectedDatasetId, apiFilters),
        ]);
      setTrends(trendsResult);
      setProducts(productsResult);
      setCategories(categoriesResult);
      setSuppliers(suppliersResult);
      setRegions(regionsResult);

      try {
        const summaryResult = await getAnalyticsSummary(selectedDatasetId);
        setSummary(summaryResult);
      } catch (err) {
        if (err instanceof AnalyticsApiError && err.code === "ANALYTICS_NOT_RUN") {
          setSummary(null);
          setNeedsRun(true);
        } else {
          throw err;
        }
      }
    } catch (err) {
      const message =
        err instanceof AnalyticsApiError || err instanceof DatasetApiError
          ? err.message
          : "Failed to load analytics.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [selectedDatasetId, filters]);

  useEffect(() => {
    void loadAnalytics();
  }, [loadAnalytics]);

  async function handleRunAnalytics() {
    if (!selectedDatasetId) return;
    setRunning(true);
    setError(null);
    try {
      await runAnalytics(selectedDatasetId);
      await loadAnalytics();
    } catch (err) {
      setError(err instanceof AnalyticsApiError ? err.message : "Failed to run analytics.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <NavBar />
      <div className="analytics-page">
        <div className="analytics-page-header">
          <h1>Analytics Dashboard</h1>
          <nav aria-label="Analytics sections">
            <Link to="/analytics/data-quality">Data Quality</Link>
            <Link to="/analytics/anomalies">Anomalies</Link>
          </nav>
        </div>

        <AnalyticsFilters
          datasets={datasets}
          selectedDatasetId={selectedDatasetId}
          onDatasetChange={setSelectedDatasetId}
          filters={filters}
          onFiltersChange={setFilters}
        />

        {datasets.length === 0 && (
          <p className="text-muted">No ready datasets available. Upload and validate one first.</p>
        )}

        {error && (
          <p className="status-error" role="alert">
            {error}
          </p>
        )}

        {loading && <p>Loading analytics…</p>}

        {needsRun && !loading && (
          <div className="panel">
            <p>No analytics have been computed for this dataset yet.</p>
            <button type="button" onClick={() => void handleRunAnalytics()} disabled={running}>
              {running ? "Running…" : "Run Analytics"}
            </button>
          </div>
        )}

        {summary && !loading && (
          <>
            <div className="analytics-page-header">
              <h2>Executive KPIs</h2>
              <button type="button" onClick={() => void handleRunAnalytics()} disabled={running}>
                {running ? "Re-running…" : "Re-run Analytics"}
              </button>
            </div>
            <div className="kpi-grid">
              {summary.kpis.map((kpi) => (
                <KPICard
                  key={kpi.kpi_name}
                  label={KPI_LABELS[kpi.kpi_name]}
                  value={kpi.value}
                  unit={kpi.unit}
                />
              ))}
            </div>
          </>
        )}

        <div className="chart-grid">
          {trends && (
            <LineChartCard
              title="Monthly Revenue Trend"
              data={trends.points.map((p) => ({ label: p.period, value: p.revenue ?? 0 }))}
            />
          )}
          {categories && (
            <BarChartCard
              title="Category Performance (Revenue)"
              data={categories.categories.map((c) => ({
                label: c.dimension,
                value: c.revenue ?? 0,
              }))}
            />
          )}
          {suppliers && (
            <BarChartCard
              title="Supplier Performance (Revenue)"
              data={suppliers.suppliers.map((s) => ({ label: s.dimension, value: s.revenue ?? 0 }))}
            />
          )}
          {regions && (
            <BarChartCard
              title="Regional Performance (Revenue)"
              data={regions.regions.map((r) => ({ label: r.dimension, value: r.revenue ?? 0 }))}
            />
          )}
          {summary && (
            <BarChartCard
              title="Channel Performance (Revenue)"
              data={summary.channel_performance.map((c) => ({
                label: c.dimension,
                value: c.revenue ?? 0,
              }))}
            />
          )}
        </div>

        {products && (
          <div className="chart-grid">
            <ProductRankingTable title="Top Selling Products" products={products.top_products} />
            <ProductRankingTable
              title="Worst Selling Products"
              products={products.worst_products}
            />
          </div>
        )}
      </div>
    </>
  );
}
