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
      <main className="flex min-h-screen items-center justify-center bg-zinc-50 text-zinc-600">
        Loading...
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#dbeafe_0%,#f8fafc_45%,#f8fafc_100%)] text-zinc-900">
      <header className="mx-auto flex h-16 w-full max-w-7xl items-center px-6">
        <Link href="/" className="font-heading text-xl font-bold text-blue-700">
          PromptDash
        </Link>
        <nav className="ml-auto flex items-center gap-2 text-sm">
          <Link href="/settings/data-sources" className="rounded-lg px-3 py-2 hover:bg-white/70">
            Data Sources
          </Link>
          <Link href="/dashboard/new" className="rounded-lg px-3 py-2 hover:bg-white/70">
            Change Sources
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 hover:bg-zinc-50"
          >
            Logout
          </button>
        </nav>
      </header>

      <main className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-4 px-6 pb-8 pt-4 lg:grid-cols-[320px_1fr]">
        <aside className="rounded-3xl border border-zinc-200 bg-white/90 p-4 shadow-xl">
          <h2 className="font-heading text-lg font-semibold">Selected Data Sources</h2>
          <p className="mt-1 text-xs text-zinc-500">{user.email}</p>

          <div className="mt-4 space-y-2">
            {selectedSources.length === 0 ? (
              <p className="rounded-xl border border-dashed border-zinc-300 p-4 text-xs text-zinc-500">
                No selected sources yet.
              </p>
            ) : (
              selectedSources.map((source) => (
                <div
                  key={source.id}
                  className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-3"
                >
                  <div>
                    <p className="text-sm font-semibold">{source.name}</p>
                    <p className="text-xs text-zinc-500">
                      {source.type === "db"
                        ? `${source.host ?? "localhost"}:${source.port ?? "5432"}`
                        : source.sizeLabel ?? "File"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSelectedSource(source.id)}
                    className="rounded-lg px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50"
                  >
                    Remove
                  </button>
                </div>
              ))
            )}
          </div>

          <h3 className="mt-5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Add Existing Source
          </h3>
          <div className="mt-2 space-y-2">
            {nonSelectedSources.length === 0 ? (
              <p className="rounded-xl border border-dashed border-zinc-300 p-3 text-xs text-zinc-500">
                All your sources are selected.
              </p>
            ) : (
              nonSelectedSources.map((source) => (
                <div
                  key={source.id}
                  className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-3"
                >
                  <p className="text-sm">{source.name}</p>
                  <button
                    type="button"
                    onClick={() => addExistingSource(source.id)}
                    className="rounded-lg bg-blue-600 px-2 py-1 text-xs font-semibold text-white hover:bg-blue-700"
                  >
                    Add
                  </button>
                </div>
              ))
            )}
          </div>

          <div className="mt-4">
            <label className="inline-flex h-10 cursor-pointer items-center rounded-xl border border-zinc-300 bg-white px-3 text-sm font-medium hover:bg-zinc-50">
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

        <section className="relative rounded-3xl border border-zinc-200 bg-white/90 p-6 shadow-xl">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="font-heading text-2xl font-bold">Empty Canvas</h1>
              <p className="mt-1 text-sm text-zinc-600">
                Add a chart block with the + button, write a prompt, then send to backend.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsComposerOpen(true)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-blue-600 text-2xl font-semibold text-white hover:bg-blue-700"
              aria-label="Add chart block"
            >
              +
            </button>
          </div>

          {charts.length === 0 ? (
            <div className="mt-6 rounded-2xl border border-dashed border-zinc-300 p-10 text-center text-sm text-zinc-500">
              No charts yet. Press + to generate your first chart from a prompt.
            </div>
          ) : (
            <div className="mt-6 space-y-4">
              {charts.map((chart) => (
                <article key={chart.id} className="rounded-2xl border border-zinc-200 bg-white p-4">
                  <p className="mb-3 text-sm font-semibold text-zinc-700">Prompt: {chart.prompt}</p>
                  {chart.isLoading ? (
                    <div className="rounded-xl border border-dashed border-zinc-300 p-8 text-sm text-zinc-500">
                      Generating chart...
                    </div>
                  ) : null}
                  {chart.error ? (
                    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                      {chart.error}
                    </div>
                  ) : null}
                  {!chart.isLoading && !chart.error && chart.html ? (
                    <div className="overflow-hidden rounded-xl border border-zinc-200">
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
            className="w-full max-w-xl rounded-2xl border border-zinc-200 bg-white p-5 shadow-2xl"
          >
            <h2 className="font-heading text-xl font-bold">Create chart from prompt</h2>
            <p className="mt-1 text-sm text-zinc-600">
              Example: show sales trend by month for electronics.
            </p>
            <textarea
              value={promptInput}
              onChange={(event) => setPromptInput(event.target.value)}
              placeholder="Write your prompt..."
              className="mt-4 min-h-32 w-full rounded-xl border border-zinc-300 p-3 text-sm outline-none ring-blue-500/30 focus:ring-4"
            />
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsComposerOpen(false)}
                className="inline-flex h-10 items-center rounded-lg border border-zinc-300 px-4 text-sm font-medium hover:bg-zinc-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting || !promptInput.trim()}
                className="inline-flex h-10 items-center rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700"
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
