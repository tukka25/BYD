"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthUser, loadCurrentUser, logoutUser } from "@/lib/auth";
import {
  bytesToSize,
  createId,
  DataSource,
  loadDataSources,
  loadSelectedSourceIds,
  saveDataSources,
  saveSelectedSourceIds,
} from "@/lib/data-sources";

interface ChartCard {
  id: string;
  prompt: string;
  html?: string;
  isLoading: boolean;
  error?: string;
}

function getExtension(filename: string): string {
  const parts = filename.split(".");
  if (parts.length < 2) return "";
  return parts[parts.length - 1].toLowerCase();
}

export default function DashboardCanvasPage() {
  const router = useRouter();
  const [isHydrated, setIsHydrated] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [allSources, setAllSources] = useState<DataSource[]>([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [promptInput, setPromptInput] = useState("");
  const [charts, setCharts] = useState<ChartCard[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inFlightRef = useRef(false);
  const pendingPromptKeysRef = useRef<Set<string>>(new Set());

  const selectedSources = useMemo(
    () => allSources.filter((source) => selectedSourceIds.includes(source.id)),
    [allSources, selectedSourceIds],
  );

  const nonSelectedSources = useMemo(
    () => allSources.filter((source) => !selectedSourceIds.includes(source.id)),
    [allSources, selectedSourceIds],
  );

  useEffect(() => {
    const currentUser = loadCurrentUser();
    if (!currentUser) {
      router.replace("/login");
      return;
    }
    setUser(currentUser);
    setAllSources(loadDataSources(currentUser.id));
    setSelectedSourceIds(loadSelectedSourceIds(currentUser.id));
    setIsHydrated(true);
  }, [router]);

  function updateSelected(nextIds: string[]) {
    if (!user) return;
    setSelectedSourceIds(nextIds);
    saveSelectedSourceIds(user.id, nextIds);
  }

  function addExistingSource(id: string) {
    if (selectedSourceIds.includes(id)) return;
    updateSelected([...selectedSourceIds, id]);
  }

  function removeSelectedSource(id: string) {
    updateSelected(selectedSourceIds.filter((sourceId) => sourceId !== id));
  }

  function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    if (!user) return;
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;

    const newSources = files.map((file) => ({
      id: createId("file"),
      name: file.name,
      type: "file" as const,
      createdAt: new Date().toISOString(),
      extension: getExtension(file.name),
      sizeLabel: bytesToSize(file.size),
    }));

    const nextAllSources = [...newSources, ...allSources];
    const nextSelected = [...newSources.map((source) => source.id), ...selectedSourceIds];

    setAllSources(nextAllSources);
    updateSelected(nextSelected);
    saveDataSources(user.id, nextAllSources);
    event.target.value = "";
  }

  async function submitPrompt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlightRef.current) return;
    const prompt = promptInput.trim();
    if (!prompt) return;
    const promptKey = prompt.toLowerCase().replace(/\s+/g, " ").trim();
    if (pendingPromptKeysRef.current.has(promptKey)) return;

    inFlightRef.current = true;
    pendingPromptKeysRef.current.add(promptKey);
    setIsSubmitting(true);
    const requestId = createId("req");
    const chartId = createId("chart");
    setPromptInput("");
    setIsComposerOpen(false);
    setCharts((prev) => [{ id: chartId, prompt, isLoading: true }, ...prev]);

    try {
      const response = await fetch("/api/dashboard/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, request_id: requestId }),
      });

      if (!response.ok) {
        const fallback = `Request failed (${response.status})`;
        const body = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? fallback);
      }
      const data = (await response.json()) as { dashboard_html?: string };

      setCharts((prev) =>
        prev.map((chart) =>
          chart.id === chartId
            ? {
                ...chart,
                isLoading: false,
                html: data.dashboard_html ?? "<p>No chart returned.</p>",
              }
            : chart,
        ),
      );
    } catch (error) {
      setCharts((prev) =>
        prev.map((chart) =>
          chart.id === chartId
            ? {
                ...chart,
                isLoading: false,
                error: error instanceof Error ? error.message : "Failed to generate chart",
              }
            : chart,
        ),
      );
    } finally {
      inFlightRef.current = false;
      pendingPromptKeysRef.current.delete(promptKey);
      setIsSubmitting(false);
    }
  }

  function handleLogout() {
    logoutUser();
    router.push("/login");
  }

  if (!isHydrated || !user) {
    return (
      <main className="app-shell flex items-center justify-center text-foreground-muted">
        Loading...
      </main>
    );
  }

  return (
    <div className="app-shell pb-8">
      <header className="border-b border-[#bcc6d4] bg-[linear-gradient(180deg,#d8dee8_0%,#cdd6e3_100%)] shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_8px_18px_rgba(163,177,198,0.35)]">
        <div className="mx-auto flex h-[5.5rem] w-full max-w-7xl items-center px-6">
        <Link href="/" className="text-embossed font-heading text-xl font-extrabold uppercase tracking-[0.04em]">
          PromptDash
        </Link>
        <nav className="ml-auto flex items-center gap-2 text-sm">
          <Link
            href="/settings/data-sources"
            className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#cfd7e3] px-3 py-2 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436] transition hover:bg-[#c5cedb]"
          >
            Data Sources
          </Link>
          <Link
            href="/dashboard/new"
            className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#cfd7e3] px-3 py-2 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436] transition hover:bg-[#c5cedb]"
          >
            Change Sources
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#cfd7e3] px-3 py-2 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436] transition hover:bg-[#c5cedb]"
          >
            Logout
          </button>
        </nav>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-4 px-6 pb-8 pt-6 lg:grid-cols-[320px_1fr]">
        <aside className="industrial-panel screw-corners p-4">
          <h2 className="text-embossed font-heading text-lg font-bold">Selected Data Sources</h2>
          <p className="label-tech mt-1">{user.email}</p>

          <div className="mt-4 space-y-2">
            {selectedSources.length === 0 ? (
              <p className="rounded-xl border border-dashed border-[#adb7c4] p-4 text-xs text-foreground-muted">
                No selected sources yet.
              </p>
            ) : (
              selectedSources.map((source) => (
                <div
                  key={source.id}
                  className="industrial-card flex items-center justify-between p-3"
                >
                  <div>
                    <p className="text-sm font-semibold">{source.name}</p>
                    <p className="font-mono text-xs text-foreground-muted">
                      {source.type === "db"
                        ? `${source.host ?? "localhost"}:${source.port ?? "5432"}`
                        : source.sizeLabel ?? "File"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSelectedSource(source.id)}
                    className="rounded-md px-2 py-1 text-xs font-bold uppercase tracking-[0.05em] text-accent transition hover:bg-[#ffd8dd]"
                  >
                    Remove
                  </button>
                </div>
              ))
            )}
          </div>

          <h3 className="label-tech mt-5">
            Add Existing Source
          </h3>
          <div className="mt-2 space-y-2">
            {nonSelectedSources.length === 0 ? (
              <p className="rounded-xl border border-dashed border-[#adb7c4] p-3 text-xs text-foreground-muted">
                All your sources are selected.
              </p>
            ) : (
              nonSelectedSources.map((source) => (
                <div
                  key={source.id}
                  className="industrial-card flex items-center justify-between p-3"
                >
                  <p className="text-sm">{source.name}</p>
                  <button
                    type="button"
                    onClick={() => addExistingSource(source.id)}
                    className="rounded-md bg-[#2f5f95] px-2 py-1 text-xs font-bold uppercase tracking-[0.05em] text-white transition hover:brightness-110"
                  >
                    Add
                  </button>
                </div>
              ))
            )}
          </div>

          <div className="mt-4">
            <label className="btn-industrial-secondary min-h-10 cursor-pointer px-3 text-xs">
              Upload Source
              <input
                type="file"
                className="hidden"
                multiple
                accept=".csv,.xls,.xlsx,.xsl,.xslz"
                onChange={handleUpload}
              />
            </label>
          </div>
        </aside>

        <section className="industrial-panel screw-corners relative p-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-embossed font-heading text-2xl font-extrabold">Empty Canvas</h1>
              <p className="mt-1 text-sm text-foreground-muted">
                Add a chart block with the + button, write a prompt, then send to backend.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsComposerOpen(true)}
              className="btn-industrial-primary h-11 w-11 rounded-full p-0 text-2xl font-semibold"
              aria-label="Add chart block"
            >
              +
            </button>
          </div>

          {charts.length === 0 ? (
            <div className="mt-6 rounded-2xl border border-dashed border-[#adb7c4] p-10 text-center text-sm text-foreground-muted">
              No charts yet. Press + to generate your first chart from a prompt.
            </div>
          ) : (
            <div className="mt-6 space-y-4">
              {charts.map((chart) => (
                <article key={chart.id} className="industrial-card p-4">
                  <p className="mb-3 text-sm font-semibold text-foreground">Prompt: {chart.prompt}</p>
                  {chart.isLoading ? (
                    <div className="rounded-xl border border-dashed border-[#adb7c4] p-8 text-sm text-foreground-muted">
                      Generating chart...
                    </div>
                  ) : null}
                  {chart.error ? (
                    <div className="rounded-xl border border-[#ff9faa] bg-[#ffd8dd] p-4 text-sm text-[#a12d39]">
                      {chart.error}
                    </div>
                  ) : null}
                  {!chart.isLoading && !chart.error && chart.html ? (
                    <div className="overflow-hidden rounded-xl border border-[#adb7c4]">
                      <iframe
                        title={`chart-${chart.id}`}
                        srcDoc={chart.html}
                        className="h-[520px] w-full"
                        sandbox="allow-scripts allow-same-origin"
                      />
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </section>
      </main>

      {isComposerOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4">
          <form
            onSubmit={submitPrompt}
            className="industrial-panel screw-corners w-full max-w-xl p-5 shadow-2xl"
          >
            <h2 className="text-embossed font-heading text-xl font-extrabold">Create chart from prompt</h2>
            <p className="mt-1 text-sm text-foreground-muted">
              Example: show sales trend by month for electronics.
            </p>
            <textarea
              value={promptInput}
              onChange={(event) => setPromptInput(event.target.value)}
              placeholder="Write your prompt..."
              className="industrial-input mt-4 min-h-32 resize-none"
            />
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsComposerOpen(false)}
                className="btn-industrial-secondary min-h-10 px-4 text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting || !promptInput.trim()}
                className="btn-industrial-primary min-h-10 px-4 text-xs"
              >
                {isSubmitting ? "Generating..." : "Send to Backend"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
