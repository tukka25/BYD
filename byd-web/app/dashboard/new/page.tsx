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
      <main className="flex min-h-screen items-center justify-center bg-zinc-50 text-zinc-600">
        Loading...
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#dbeafe_0%,#f8fafc_45%,#f8fafc_100%)] text-zinc-900">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center px-6">
        <Link href="/" className="font-heading text-xl font-bold text-blue-700">
          PromptDash
        </Link>
        <nav className="ml-auto flex items-center gap-2 text-sm">
          <Link href="/settings/data-sources" className="rounded-lg px-3 py-2 hover:bg-white/70">
            Data Sources
          </Link>
          <span className="rounded-lg bg-blue-100 px-3 py-2 text-blue-700">Create Dashboard</span>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 hover:bg-zinc-50"
          >
            Logout
          </button>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-12 pt-8">
        {error ? (
          <p className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>
        ) : null}
        <section className="rounded-3xl border border-zinc-200 bg-white/85 p-6 shadow-xl">
          <h1 className="font-heading text-3xl font-bold">Create New Dashboard</h1>
          <p className="mt-2 text-sm text-zinc-600">
            Select data sources for this dashboard. User: {user.email}
          </p>

          {sources.length === 0 ? (
            <div className="mt-6 rounded-xl border border-dashed border-zinc-300 p-8 text-center">
              <p className="text-sm text-zinc-600">No sources available for your account.</p>
              <Link
                href="/settings/data-sources"
                className="mt-3 inline-flex h-10 items-center rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700"
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
                    className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition ${
                      isSelected
                        ? "border-blue-500 bg-blue-50"
                        : "border-zinc-200 bg-white hover:border-zinc-300"
                    }`}
                  >
                    <div>
                      <p className="text-sm font-semibold">{source.name}</p>
                      <p className="text-xs text-zinc-500">
                        {source.type === "db"
                          ? `${source.host ?? "localhost"}:${source.port ?? "5432"}`
                          : source.sizeLabel ?? "File"}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-semibold ${
                        isSelected ? "bg-blue-600 text-white" : "bg-zinc-100 text-zinc-600"
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
              className="inline-flex h-10 items-center rounded-lg border border-zinc-300 bg-white px-4 text-sm font-medium hover:bg-zinc-50"
            >
              Upload or Connect More
            </Link>
            <button
              type="button"
              onClick={handleCreateDashboard}
              disabled={!selectedIds.length}
              className="inline-flex h-10 items-center rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Open Canvas
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
