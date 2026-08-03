import { useCallback, useEffect, useState } from "react";

import { DatasetApiError, listDatasets, type Dataset } from "../api/datasets";
import { DatasetDetail } from "../components/DatasetDetail";
import { DatasetList } from "../components/DatasetList";
import { NavBar } from "../components/NavBar";
import { UploadDropzone } from "../components/UploadDropzone";

export function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listDatasets();
      setDatasets(result);
    } catch (err) {
      setError(err instanceof DatasetApiError ? err.message : "Failed to load datasets.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function handleUploaded(dataset: Dataset) {
    setDatasets((prev) => [dataset, ...prev]);
    setSelectedId(dataset.id);
  }

  function handleDatasetUpdated(dataset: Dataset) {
    setDatasets((prev) => prev.map((d) => (d.id === dataset.id ? dataset : d)));
  }

  function handleDatasetDeleted(id: string) {
    setDatasets((prev) => prev.filter((d) => d.id !== id));
    setSelectedId((current) => (current === id ? null : current));
  }

  const selectedDataset = datasets.find((d) => d.id === selectedId) ?? null;

  return (
    <>
      <NavBar />
      <div className="datasets-page">
        <h1>Datasets</h1>

        <UploadDropzone onUploaded={handleUploaded} />

        <DatasetList
          datasets={datasets}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={loading}
          error={error}
        />

        {selectedDataset && (
          <DatasetDetail
            dataset={selectedDataset}
            onDatasetUpdated={handleDatasetUpdated}
            onDatasetDeleted={handleDatasetDeleted}
          />
        )}
      </div>
    </>
  );
}
