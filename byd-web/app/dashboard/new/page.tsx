"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthUser, getAccessToken, loadCurrentUser, logoutUser } from "@/lib/auth";
import { authorizedFetch, BackendDataSource, mapBackendDataSource } from "@/lib/backend";
import {
  DataSource,
  saveSelectedSourceIds,
} from "@/lib/data-sources";

export default function CreateDashboardPage() {
  const router = useRouter();
  const [isHydrated, setIsHydrated] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const currentUser = loadCurrentUser();
    const currentToken = getAccessToken();
    if (!currentUser || !currentToken) {
      router.replace("/login");
      return;
    }

    setUser(currentUser);
    setToken(currentToken);
    authorizedFetch<BackendDataSource[]>("/api/v1/data-sources", currentToken)
      .then((items) => setSources(items.map(mapBackendDataSource)))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load sources"));
    setIsHydrated(true);
  }, [router]);

  function toggleSource(id: string) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((sourceId) => sourceId !== id) : [...prev, id],
    );
  }

  async function handleCreateDashboard() {
    if (!selectedIds.length || !user || !token) return;
    try {
      const created = await authorizedFetch<{ id: string }>("/api/v1/dashboard", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Untitled Dashboard",
          data_source_ids: selectedIds,
        }),
      });
      saveSelectedSourceIds(user.id, selectedIds);
      router.push(`/dashboard/new-canvas?dashboardId=${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create dashboard");
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
    <div className="app-shell pb-12">
      <header className="border-b border-[#bcc6d4] bg-[linear-gradient(180deg,#d8dee8_0%,#cdd6e3_100%)] shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_8px_18px_rgba(163,177,198,0.35)]">
        <div className="mx-auto flex h-[5.5rem] w-full max-w-6xl items-center px-6">
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
          <span className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#bcc7d6] px-3 py-2 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436]">
            Create Dashboard
          </span>
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

      <main className="mx-auto max-w-6xl px-6 pb-12 pt-8">
        {error ? (
          <p className="mb-4 rounded-xl border border-[#ff9faa] bg-[#ffd8dd] p-3 text-sm text-[#a12d39]">{error}</p>
        ) : null}
        <section className="industrial-panel screw-corners p-6">
          <p className="label-tech">Provision Canvas</p>
          <h1 className="text-embossed mt-2 font-heading text-3xl font-extrabold">Create New Dashboard</h1>
          <p className="mt-2 text-sm text-foreground-muted">
            Select data sources for this dashboard. User: {user.email}
          </p>

          {sources.length === 0 ? (
            <div className="mt-6 rounded-xl border border-dashed border-[#adb7c4] p-8 text-center">
              <p className="text-sm text-foreground-muted">No sources available for your account.</p>
              <Link
                href="/settings/data-sources"
                className="btn-industrial-primary mt-3"
              >
                Add Data Sources
              </Link>
            </div>
          ) : (
            <div className="mt-6 space-y-3">
              {sources.map((source) => {
                const isSelected = selectedIds.includes(source.id);
                return (
                  <button
                    key={source.id}
                    type="button"
                    onClick={() => toggleSource(source.id)}
                    className={`industrial-card flex w-full items-center justify-between px-4 py-3 text-left transition ${
                      isSelected
                        ? "border-[#ff8b97] bg-[#ffd8dd]"
                        : "hover:border-[#aab6c8]"
                    }`}
                  >
                    <div>
                      <p className="text-sm font-semibold">{source.name}</p>
                      <p className="font-mono text-xs text-foreground-muted">
                        {source.type === "db"
                          ? `${source.host ?? "localhost"}:${source.port ?? "5432"}`
                          : source.sizeLabel ?? "File"}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-[0.05em] ${
                        isSelected ? "bg-[#ff4757] text-white" : "bg-[#cfd7e3] text-[#2d3436]"
                      }`}
                    >
                      {isSelected ? "Selected" : "Select"}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <Link
              href="/settings/data-sources"
              className="btn-industrial-secondary"
            >
              Upload or Connect More
            </Link>
            <button
              type="button"
              onClick={handleCreateDashboard}
              disabled={!selectedIds.length}
              className="btn-industrial-primary"
            >
              Open Canvas
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
