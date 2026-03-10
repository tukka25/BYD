"use client";

import Link from "next/link";
import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthUser, loadCurrentUser, logoutUser } from "@/lib/auth";
import {
  bytesToSize,
  createId,
  DataSource,
  loadDataSources,
  saveDataSources,
} from "@/lib/data-sources";

interface DbFormState {
  name: string;
  host: string;
  port: string;
  database: string;
}

function getExtension(filename: string): string {
  const parts = filename.split(".");
  if (parts.length < 2) return "";
  return parts[parts.length - 1].toLowerCase();
}

export default function DataSourcesPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [isHydrated, setIsHydrated] = useState(false);
  const [isAddingDb, setIsAddingDb] = useState(false);
  const [dbForm, setDbForm] = useState<DbFormState>({
    name: "",
    host: "localhost",
    port: "5432",
    database: "",
  });

  const fileSources = useMemo(
    () => sources.filter((source) => source.type === "file"),
    [sources],
  );
  const dbSources = useMemo(
    () => sources.filter((source) => source.type === "db"),
    [sources],
  );

  useEffect(() => {
    const currentUser = loadCurrentUser();
    if (!currentUser) {
      router.replace("/login");
      return;
    }
    setUser(currentUser);
    setSources(loadDataSources(currentUser.id));
    setIsHydrated(true);
  }, [router]);

  function persist(nextSources: DataSource[]) {
    if (!user) return;
    setSources(nextSources);
    saveDataSources(user.id, nextSources);
  }

  function handleUpload(event: ChangeEvent<HTMLInputElement>) {
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

    persist([...newSources, ...sources]);
    event.target.value = "";
  }

  function removeSource(id: string) {
    persist(sources.filter((source) => source.id !== id));
  }

  function addDbConnection() {
    if (!dbForm.name.trim()) return;
    const connection: DataSource = {
      id: createId("db"),
      name: dbForm.name.trim(),
      type: "db",
      createdAt: new Date().toISOString(),
      status: "connected",
      host: dbForm.host.trim() || "localhost",
      port: dbForm.port.trim() || "5432",
      database: dbForm.database.trim(),
    };
    persist([connection, ...sources]);
    setDbForm({ name: "", host: "localhost", port: "5432", database: "" });
    setIsAddingDb(false);
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
          <Link href="/dashboard/new" className="rounded-lg px-3 py-2 hover:bg-white/70">
            Create Dashboard
          </Link>
          <span className="rounded-lg bg-blue-100 px-3 py-2 text-blue-700">Data Sources</span>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 hover:bg-zinc-50"
          >
            Logout
          </button>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 pb-12 pt-8">
        <section className="rounded-3xl border border-zinc-200 bg-white/85 p-6 shadow-xl">
          <h1 className="font-heading text-3xl font-bold">Data Sources</h1>
          <p className="mt-2 text-sm text-zinc-600">
            User: {user.email}. These sources belong only to this account.
          </p>
        </section>

        <section className="rounded-3xl border border-zinc-200 bg-white/85 p-6 shadow-xl">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-heading text-xl font-semibold">Files</h2>
            <label className="inline-flex h-10 cursor-pointer items-center rounded-xl bg-zinc-900 px-4 text-sm font-medium text-white hover:bg-zinc-800">
              Upload files
              <input
                type="file"
                className="hidden"
                multiple
                accept=".csv,.xls,.xlsx,.xsl,.xslz"
                onChange={handleUpload}
              />
            </label>
          </div>

          {fileSources.length === 0 ? (
            <p className="rounded-xl border border-dashed border-zinc-300 p-6 text-sm text-zinc-500">
              No uploaded files yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {fileSources.map((source) => (
                <li
                  key={source.id}
                  className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-4"
                >
                  <div>
                    <p className="text-sm font-semibold">{source.name}</p>
                    <p className="text-xs text-zinc-500">
                      {source.sizeLabel ?? "Unknown size"} •{" "}
                      {new Date(source.createdAt).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSource(source.id)}
                    className="rounded-lg px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-3xl border border-zinc-200 bg-white/85 p-6 shadow-xl">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-heading text-xl font-semibold">Database Connections</h2>
            <button
              type="button"
              onClick={() => setIsAddingDb((prev) => !prev)}
              className="inline-flex h-10 items-center rounded-xl border border-zinc-300 bg-white px-4 text-sm font-medium hover:bg-zinc-50"
            >
              {isAddingDb ? "Cancel" : "Add connection"}
            </button>
          </div>

          {isAddingDb ? (
            <div className="mb-4 grid gap-3 rounded-xl border border-zinc-200 bg-white p-4 md:grid-cols-2">
              <input
                value={dbForm.name}
                onChange={(event) => setDbForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="Connection name"
                className="h-10 rounded-lg border border-zinc-300 px-3 text-sm outline-none ring-blue-500/30 focus:ring-4"
              />
              <input
                value={dbForm.host}
                onChange={(event) => setDbForm((prev) => ({ ...prev, host: event.target.value }))}
                placeholder="Host"
                className="h-10 rounded-lg border border-zinc-300 px-3 text-sm outline-none ring-blue-500/30 focus:ring-4"
              />
              <input
                value={dbForm.port}
                onChange={(event) => setDbForm((prev) => ({ ...prev, port: event.target.value }))}
                placeholder="Port"
                className="h-10 rounded-lg border border-zinc-300 px-3 text-sm outline-none ring-blue-500/30 focus:ring-4"
              />
              <input
                value={dbForm.database}
                onChange={(event) =>
                  setDbForm((prev) => ({ ...prev, database: event.target.value }))
                }
                placeholder="Database name"
                className="h-10 rounded-lg border border-zinc-300 px-3 text-sm outline-none ring-blue-500/30 focus:ring-4"
              />
              <button
                type="button"
                onClick={addDbConnection}
                className="inline-flex h-10 items-center justify-center rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700"
              >
                Save Connection
              </button>
            </div>
          ) : null}

          {dbSources.length === 0 ? (
            <p className="rounded-xl border border-dashed border-zinc-300 p-6 text-sm text-zinc-500">
              No database connections yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {dbSources.map((source) => (
                <li
                  key={source.id}
                  className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-4"
                >
                  <div>
                    <p className="text-sm font-semibold">{source.name}</p>
                    <p className="text-xs text-zinc-500">
                      {source.host}:{source.port}
                      {source.database ? ` • ${source.database}` : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSource(source.id)}
                    className="rounded-lg px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}

