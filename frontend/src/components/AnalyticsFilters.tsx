import { useId } from "react";

import type { Dataset } from "../api/datasets";

export interface AnalyticsFilterState {
  dateFrom: string;
  dateTo: string;
  category: string;
  supplier: string;
  region: string;
  channel: string;
}

export const EMPTY_ANALYTICS_FILTERS: AnalyticsFilterState = {
  dateFrom: "",
  dateTo: "",
  category: "",
  supplier: "",
  region: "",
  channel: "",
};

interface AnalyticsFiltersProps {
  datasets: Dataset[];
  selectedDatasetId: string | null;
  onDatasetChange: (id: string) => void;
  filters: AnalyticsFilterState;
  onFiltersChange: (filters: AnalyticsFilterState) => void;
}

/** Dataset selector plus the shared filter bar (date range, category,
 * supplier, region, channel) used across every analytics page. */
export function AnalyticsFilters({
  datasets,
  selectedDatasetId,
  onDatasetChange,
  filters,
  onFiltersChange,
}: AnalyticsFiltersProps) {
  const datasetSelectId = useId();
  const dateFromId = useId();
  const dateToId = useId();
  const categoryId = useId();
  const supplierId = useId();
  const regionId = useId();
  const channelId = useId();

  function update(field: keyof AnalyticsFilterState, value: string) {
    onFiltersChange({ ...filters, [field]: value });
  }

  return (
    <div className="panel analytics-filters" aria-label="Analytics filters">
      <div className="filter-field">
        <label htmlFor={datasetSelectId}>Dataset</label>
        <select
          id={datasetSelectId}
          value={selectedDatasetId ?? ""}
          onChange={(event) => onDatasetChange(event.target.value)}
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

      <div className="filter-field">
        <label htmlFor={dateFromId}>From</label>
        <input
          id={dateFromId}
          type="date"
          value={filters.dateFrom}
          onChange={(event) => update("dateFrom", event.target.value)}
        />
      </div>

      <div className="filter-field">
        <label htmlFor={dateToId}>To</label>
        <input
          id={dateToId}
          type="date"
          value={filters.dateTo}
          onChange={(event) => update("dateTo", event.target.value)}
        />
      </div>

      <div className="filter-field">
        <label htmlFor={categoryId}>Category</label>
        <input
          id={categoryId}
          type="text"
          value={filters.category}
          onChange={(event) => update("category", event.target.value)}
        />
      </div>

      <div className="filter-field">
        <label htmlFor={supplierId}>Supplier</label>
        <input
          id={supplierId}
          type="text"
          value={filters.supplier}
          onChange={(event) => update("supplier", event.target.value)}
        />
      </div>

      <div className="filter-field">
        <label htmlFor={regionId}>Region</label>
        <input
          id={regionId}
          type="text"
          value={filters.region}
          onChange={(event) => update("region", event.target.value)}
        />
      </div>

      <div className="filter-field">
        <label htmlFor={channelId}>Channel</label>
        <input
          id={channelId}
          type="text"
          value={filters.channel}
          onChange={(event) => update("channel", event.target.value)}
        />
      </div>
    </div>
  );
}
