import { useId, useRef, useState } from "react";
import type { DragEvent, KeyboardEvent } from "react";

import {
  ACCEPTED_FILE_EXTENSIONS,
  DatasetApiError,
  MAX_UPLOAD_SIZE_BYTES,
  uploadDataset,
  type Dataset,
} from "../api/datasets";

interface UploadDropzoneProps {
  onUploaded: (dataset: Dataset) => void;
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

function hasAcceptedExtension(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ACCEPTED_FILE_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; percent: number; fileName: string }
  | { kind: "error"; message: string; findings: { message: string }[] }
  | { kind: "success"; fileName: string };

export function UploadDropzone({ onUploaded }: UploadDropzoneProps) {
  const inputId = useId();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [state, setState] = useState<UploadState>({ kind: "idle" });

  async function handleFile(file: File) {
    if (!hasAcceptedExtension(file.name)) {
      setState({
        kind: "error",
        message: `Unsupported file type. Accepted formats: ${ACCEPTED_FILE_EXTENSIONS.join(", ")}.`,
        findings: [],
      });
      return;
    }

    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setState({
        kind: "error",
        message: `File is too large. Maximum size is ${formatBytes(MAX_UPLOAD_SIZE_BYTES)}.`,
        findings: [],
      });
      return;
    }

    setState({ kind: "uploading", percent: 0, fileName: file.name });
    try {
      const dataset = await uploadDataset(file, undefined, (percent) => {
        setState((prev) =>
          prev.kind === "uploading" ? { ...prev, percent } : prev,
        );
      });
      setState({ kind: "success", fileName: file.name });
      onUploaded(dataset);
    } catch (err) {
      if (err instanceof DatasetApiError) {
        setState({ kind: "error", message: err.message, findings: err.findings });
      } else {
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Upload failed.",
          findings: [],
        });
      }
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  }

  function handleInputChange() {
    const file = fileInputRef.current?.files?.[0];
    if (file) void handleFile(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInputRef.current?.click();
    }
  }

  const uploading = state.kind === "uploading";

  return (
    <div className="panel">
      <h2>Upload a dataset</h2>
      <p className="dropzone-hint">
        Accepted formats: {ACCEPTED_FILE_EXTENSIONS.join(", ")} · Max size:{" "}
        {formatBytes(MAX_UPLOAD_SIZE_BYTES)}
      </p>

      <label htmlFor={inputId} className="visually-hidden">
        Choose a dataset file to upload
      </label>
      <div
        role="button"
        tabIndex={0}
        aria-disabled={uploading}
        className={dragging ? "dropzone dragging" : "dropzone"}
        onClick={() => !uploading && fileInputRef.current?.click()}
        onKeyDown={handleKeyDown}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <p>Drag and drop a CSV or Excel file here, or click to browse.</p>
        <input
          ref={fileInputRef}
          id={inputId}
          type="file"
          accept={ACCEPTED_FILE_EXTENSIONS.join(",")}
          onChange={handleInputChange}
          disabled={uploading}
          style={{ display: "none" }}
        />
      </div>

      {state.kind === "uploading" && (
        <div>
          <p>
            Uploading {state.fileName}… {state.percent}%
          </p>
          <div
            className="progress-bar"
            role="progressbar"
            aria-valuenow={state.percent}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className="progress-bar-fill" style={{ width: `${state.percent}%` }} />
          </div>
        </div>
      )}

      {state.kind === "success" && (
        <p className="status-ok" role="status">
          {state.fileName} uploaded successfully.
        </p>
      )}

      {state.kind === "error" && (
        <div className="status-error" role="alert">
          <p>{state.message}</p>
          {state.findings.length > 0 && (
            <ul className="finding-list">
              {state.findings.map((finding, index) => (
                <li key={index} className="finding-item">
                  {finding.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
