"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Database, FileSpreadsheet, Trash2, Upload } from "lucide-react";
import { AppShell, PageHeader } from "@/components/app-shell";
import { Button, Chip, EmptyState, IconButton, Panel } from "@/components/ui";
import { getAccessToken } from "@/lib/auth";
import { ConnectDatabase } from "@/components/sources";
import {
  ALLOWED_EXTENSIONS,
  deleteSource,
  listSources,
  sourceSubtitle,
  uploadSource,
  type Source,
} from "@/lib/sources";

export default function DataPage() {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const token = typeof window !== "undefined" ? getAccessToken() : null;

  async function refresh() {
    const token = getAccessToken();
    if (!token) return;
    try {
      setSources(await listSources(token));
    } catch {
      setSources([]);
      setError("Could not load your data sources.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleFiles(files: FileList | null) {
    const token = getAccessToken();
    if (!files || files.length === 0 || !token) return;
    setError(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await uploadSource(token, file);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function remove(id: string) {
    const token = getAccessToken();
    if (!token) return;
    setSources((current) => current?.filter((s) => s.id !== id) ?? null);
    try {
      await deleteSource(token, id);
    } catch {
      setError("Could not remove that source.");
      void refresh();
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="Data sources"
        lead="Files stay on this machine. Nothing is uploaded anywhere else, and the model reads them locally."
        actions={
          <>
            <Button variant="secondary" onClick={() => setConnecting((v) => !v)}>
              <Database size={16} strokeWidth={2.25} />
              Connect a database
            </Button>
            <Button variant="primary" onClick={() => fileInput.current?.click()} disabled={uploading}>
              <Upload size={16} strokeWidth={2.25} />
              {uploading ? "Uploading…" : "Upload file"}
            </Button>
          </>
        }
      />

      <div className="app-scroll px-5 sm:px-8 pb-16">
        <input
          ref={fileInput}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.join(",")}
          className="sr-only"
          onChange={(event) => {
            void handleFiles(event.target.files);
            event.target.value = "";
          }}
        />

        {error ? (
          <div className="mb-4 flex items-start gap-2 rounded-[var(--r-card)] bg-coral-wash px-4 py-3 text-[13px] text-[#b5301c]">
            <AlertTriangle size={16} strokeWidth={2.25} className="mt-px shrink-0" />
            <span className="flex-1">{error}</span>
            <button onClick={() => setError(null)} className="font-semibold underline">
              Dismiss
            </button>
          </div>
        ) : null}

        {connecting && token ? (
          <div className="mb-6">
            <ConnectDatabase
              token={token}
              onCancel={() => setConnecting(false)}
              onConnected={(source) => {
                setSources((current) => [source, ...(current ?? [])]);
                setConnecting(false);
              }}
            />
          </div>
        ) : null}

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void handleFiles(event.dataTransfer.files);
          }}
          className={[
            "mb-6 rounded-[var(--r-panel)] border-2 border-dashed px-6 py-10 text-center",
            "transition-colors duration-200 ease-[var(--ease-out)]",
            dragging ? "border-violet bg-violet-wash" : "border-hairline-strong bg-surface",
          ].join(" ")}
        >
          <p className="font-display text-[17px] font-semibold text-ink">
            {dragging ? "Drop to upload" : "Drop a CSV or Excel file here"}
          </p>
          <p className="mt-1 text-[13px] text-muted">
            {ALLOWED_EXTENSIONS.join(", ")} · or{" "}
            <button
              onClick={() => fileInput.current?.click()}
              className="font-semibold text-violet underline underline-offset-2"
            >
              choose a file
            </button>
          </p>
        </div>

        {sources === null ? (
          <div className="flex flex-col gap-3">
            <div className="h-[72px] rounded-[var(--r-card)] generating" />
            <div className="h-[72px] rounded-[var(--r-card)] generating" />
          </div>
        ) : sources.length === 0 ? (
          <Panel>
            <EmptyState
              icon={<FileSpreadsheet size={20} strokeWidth={2.25} />}
              title="No data yet"
              body="Upload a spreadsheet or connect a database, and it becomes available to every report you create."
              action={
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <Button variant="primary" onClick={() => fileInput.current?.click()}>
                    Upload a file
                  </Button>
                  <Button variant="secondary" onClick={() => setConnecting(true)}>
                    Connect a database
                  </Button>
                </div>
              }
            />
          </Panel>
        ) : (
          <ul className="flex flex-col gap-3">
            {sources.map((source) => (
              <li key={source.id}>
                <Panel className="flex items-center gap-4 p-4">
                  <span className="grid size-11 shrink-0 place-items-center rounded-[var(--r-control)] bg-violet-wash text-violet">
                    {source.source_type === "db" ? (
                      <Database size={19} strokeWidth={2.25} />
                    ) : (
                      <FileSpreadsheet size={19} strokeWidth={2.25} />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-[14.5px] text-ink">
                      {source.display_name}
                    </p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[12.5px] text-muted">
                      {source.source_type === "db" ? (
                        <span className="font-mono">{sourceSubtitle(source)}</span>
                      ) : (
                        <>
                          {source.original_filename ? (
                            <span className="font-mono">{source.original_filename}</span>
                          ) : null}
                          {sourceSubtitle(source) ? (
                            <span className="tabular">{sourceSubtitle(source)}</span>
                          ) : null}
                        </>
                      )}
                    </p>
                  </div>
                  <Chip tone={source.source_type === "db" ? "violet" : "neutral"}>
                    {source.source_type === "db" ? (source.db_type ?? "database") : "File"}
                  </Chip>
                  <Chip tone={source.status === "active" ? "teal" : "neutral"}>
                    {source.status === "active" ? "Ready" : (source.status ?? "unknown")}
                  </Chip>
                  <IconButton label={`Remove ${source.display_name}`} tone="danger" onClick={() => remove(source.id)}>
                    <Trash2 size={16} strokeWidth={2.25} />
                  </IconButton>
                </Panel>
              </li>
            ))}
          </ul>
        )}
      </div>
    </AppShell>
  );
}
