"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, FileSpreadsheet, Upload } from "lucide-react";
import { AppShell, PageHeader } from "@/components/app-shell";
import { Button, Field, Panel, inputClass } from "@/components/ui";
import { getAccessToken } from "@/lib/auth";
import { createReport } from "@/lib/reports";
import { ALLOWED_EXTENSIONS, formatSize, listSources, uploadSource, type Source } from "@/lib/sources";

export default function NewReportPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    listSources(token)
      .then(setSources)
      .catch(() => setSources([]));
  }, []);

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((s) => s !== id) : [...current, id],
    );
  }

  async function upload(files: FileList | null) {
    const token = getAccessToken();
    if (!files?.length || !token) return;
    setUploading(true);
    setError(null);
    try {
      const created = await uploadSource(token, files[0]);
      setSources((current) => [created, ...current]);
      setSelected((current) => [...current, created.id]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function submit() {
    const token = getAccessToken();
    if (!token || !title.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const report = await createReport(token, {
        title: title.trim(),
        description: description.trim() || undefined,
        dataSourceIds: selected,
      });
      router.push(`/reports/${report.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the report.");
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="New report"
        lead="Name it, choose which data it can read, then start asking questions on the canvas."
      />

      <div className="app-scroll px-5 pb-24 sm:px-8">
        <div className="max-w-2xl">
        {error ? (
          <div className="mb-4 flex items-start gap-2 rounded-[var(--r-card)] bg-coral-wash px-4 py-3 text-[13px] text-[#b5301c]">
            <AlertTriangle size={16} strokeWidth={2.25} className="mt-px shrink-0" />
            <span className="flex-1">{error}</span>
          </div>
        ) : null}

        <Panel className="p-6">
          <div className="flex flex-col gap-5">
            <Field label="Report name" htmlFor="title">
              <input
                id="title"
                value={title}
                autoFocus
                onChange={(event) => setTitle(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void submit();
                }}
                placeholder="Q1 revenue review"
                className={inputClass}
              />
            </Field>

            <Field label="Description" hint="Optional. Shown under the title on the canvas." htmlFor="description">
              <input
                id="description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What this report is for"
                className={inputClass}
              />
            </Field>

            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-[13px] font-semibold text-ink">Data for this report</span>
                <button
                  onClick={() => fileInput.current?.click()}
                  disabled={uploading}
                  className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-violet disabled:opacity-50"
                >
                  <Upload size={14} strokeWidth={2.25} />
                  {uploading ? "Uploading…" : "Upload new"}
                </button>
              </div>
              <input
                ref={fileInput}
                type="file"
                accept={ALLOWED_EXTENSIONS.join(",")}
                className="sr-only"
                onChange={(event) => {
                  void upload(event.target.files);
                  event.target.value = "";
                }}
              />

              {sources.length === 0 ? (
                <p className="rounded-[var(--r-card)] bg-sunken px-4 py-3 text-[13px] text-muted">
                  No files yet. Upload one, or leave this empty and the report will search
                  everything you have.
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {sources.map((source) => {
                    const on = selected.includes(source.id);
                    return (
                      <li key={source.id}>
                        <button
                          onClick={() => toggle(source.id)}
                          aria-pressed={on}
                          className={[
                            "flex w-full items-center gap-3 rounded-[var(--r-card)] px-3.5 py-3 text-left",
                            "transition-colors duration-150 ease-[var(--ease-out)]",
                            on ? "bg-violet-wash ring-1 ring-inset ring-violet" : "bg-sunken hover:bg-[#e0e0e7]",
                          ].join(" ")}
                        >
                          <span
                            className={[
                              "grid size-5 shrink-0 place-items-center rounded-[6px]",
                              on ? "bg-violet text-white" : "bg-surface ring-1 ring-inset ring-hairline-strong",
                            ].join(" ")}
                          >
                            {on ? <Check size={13} strokeWidth={3} /> : null}
                          </span>
                          <FileSpreadsheet size={16} strokeWidth={2.25} className="shrink-0 text-muted" />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13.5px] font-semibold text-ink">
                              {source.display_name}
                            </span>
                            {formatSize(source.file_size_bytes) ? (
                              <span className="block text-[12px] text-muted tabular">
                                {formatSize(source.file_size_bytes)}
                              </span>
                            ) : null}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              <p className="mt-2 text-[12px] text-muted">
                Leave all unticked to let the report pick from every source you have.
              </p>
            </div>

            <div className="flex items-center gap-2 pt-1">
              <Button variant="primary" onClick={submit} disabled={!title.trim() || busy}>
                {busy ? "Creating…" : "Create report"}
              </Button>
              <Button variant="ghost" onClick={() => router.back()}>
                Cancel
              </Button>
            </div>
          </div>
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}
