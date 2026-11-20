"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { AppShell, PageHeader } from "@/components/app-shell";
import { Button, Field, Panel, inputClass } from "@/components/ui";
import { getAccessToken } from "@/lib/auth";
import { createReport } from "@/lib/reports";
import { SourceManager } from "@/components/sources";
import { listSources, type Source } from "@/lib/sources";

export default function NewReportPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const token = typeof window !== "undefined" ? getAccessToken() : null;

  useEffect(() => {
    if (!token) return;
    listSources(token)
      .then(setSources)
      .catch(() => setSources([]));
  }, [token]);

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((s) => s !== id) : [...current, id],
    );
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
          <div className="mb-4 flex items-start gap-2 rounded-[var(--r-card)] bg-coral-wash px-4 py-3 text-[13px] text-coral-ink">
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
              <span className="mb-1.5 block text-[13px] font-semibold text-ink">
                Data for this report
              </span>
              {token ? (
                <SourceManager
                  token={token}
                  sources={sources}
                  onSourcesChange={setSources}
                  selected={selected}
                  onToggle={toggle}
                  emptyNote="Nothing yet. Upload a file or connect a database — or leave this empty and the report searches everything you have."
                />
              ) : null}
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
