"use client";

import Link from "next/link";
import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthUser, getAccessToken, loadCurrentUser, logoutUser } from "@/lib/auth";
import { authorizedFetch, BackendDataSource, mapBackendDataSource } from "@/lib/backend";
import {
  DataSource,
} from "@/lib/data-sources";

interface DbFormState {
  name: string;
  dbType: string;
  host: string;
  port: string;
  database: string;
  username: string;
  password: string;
}

export default function DataSourcesPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [isHydrated, setIsHydrated] = useState(false);
  const [isAddingDb, setIsAddingDb] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dbForm, setDbForm] = useState<DbFormState>({
    name: "",
    dbType: "postgresql",
    host: "localhost",
    port: "5432",
    database: "",
    username: "",
    password: "",
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
    const currentToken = getAccessToken();
    if (!currentUser || !currentToken) {
      router.replace("/login");
      return;
    }
    setUser(currentUser);
    setToken(currentToken);
    setIsHydrated(true);
    authorizedFetch<BackendDataSource[]>("/api/v1/data-sources", currentToken)
      .then((items) => setSources(items.map(mapBackendDataSource)))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load data sources"));
  }, [router]);

  async function refreshSources(activeToken: string) {
    const items = await authorizedFetch<BackendDataSource[]>("/api/v1/data-sources", activeToken);
    setSources(items.map(mapBackendDataSource));
  }

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    if (!token) return;
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;

    try {
      for (const file of files) {
        const formData = new FormData();
        formData.append("file", file);
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1/data-sources/upload`,
          {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
          },
        );
        if (!response.ok) {
          const body = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(body?.detail ?? `Upload failed (${response.status})`);
        }
      }
      await refreshSources(token);
      event.target.value = "";
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload file");
    }
  }

  async function removeSource(id: string) {
    if (!token) return;
    try {
      await authorizedFetch<void>(`/api/v1/data-sources/${id}`, token, { method: "DELETE" });
      await refreshSources(token);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove data source");
    }
  }

  async function addDbConnection() {
    if (!token || !dbForm.name.trim()) return;
    try {
      await authorizedFetch<BackendDataSource>("/api/v1/data-sources/db-connection", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: dbForm.name.trim(),
          db_type: dbForm.dbType.trim() || "postgresql",
          db_host: dbForm.host.trim() || "localhost",
          db_port: Number(dbForm.port.trim() || "5432"),
          db_name: dbForm.database.trim(),
          db_username: dbForm.username.trim(),
          db_password: dbForm.password,
        }),
      });
      await refreshSources(token);
      setDbForm({
        name: "",
        dbType: "postgresql",
        host: "localhost",
        port: "5432",
        database: "",
        username: "",
        password: "",
      });
      setIsAddingDb(false);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add connection");
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
            href="/dashboard/new"
            className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#cfd7e3] px-3 py-2 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436] transition hover:bg-[#c5cedb]"
          >
            Create Dashboard
          </Link>
          <span className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#bcc7d6] px-3 py-2 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436]">
            Data Sources
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

      <main className="mx-auto max-w-6xl space-y-6 px-6 pb-12 pt-8">
        {error ? (
          <p className="rounded-xl border border-[#ff9faa] bg-[#ffd8dd] p-3 text-sm text-[#a12d39]">{error}</p>
        ) : null}
        <section className="industrial-panel screw-corners p-6">
          <p className="label-tech">Source Registry</p>
          <h1 className="text-embossed mt-2 font-heading text-3xl font-extrabold">Data Sources</h1>
          <p className="mt-2 text-sm text-foreground-muted">
            User: {user.email}. These sources belong only to this account.
          </p>
        </section>

        <section className="industrial-panel screw-corners p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-embossed font-heading text-xl font-bold">Files</h2>
            <label className="btn-industrial-secondary min-h-10 cursor-pointer px-4 text-xs">
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
            <p className="rounded-xl border border-dashed border-[#adb7c4] p-6 text-sm text-foreground-muted">
              No uploaded files yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {fileSources.map((source) => (
                <li
                  key={source.id}
                  className="industrial-card flex items-center justify-between p-4"
                >
                  <div>
                    <p className="text-sm font-semibold">{source.name}</p>
                    <p className="font-mono text-xs text-foreground-muted">
                      {source.sizeLabel ?? "Unknown size"} •{" "}
                      {new Date(source.createdAt).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSource(source.id)}
                    className="rounded-md px-3 py-1.5 text-xs font-bold uppercase tracking-[0.05em] text-accent transition hover:bg-[#ffd8dd]"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="industrial-panel screw-corners p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-embossed font-heading text-xl font-bold">Database Connections</h2>
            <button
              type="button"
              onClick={() => setIsAddingDb((prev) => !prev)}
              className="btn-industrial-secondary min-h-10 px-4 text-xs"
            >
              {isAddingDb ? "Cancel" : "Add connection"}
            </button>
          </div>

          {isAddingDb ? (
            <div className="industrial-card mb-4 grid gap-3 p-4 md:grid-cols-2">
              <input
                value={dbForm.name}
                onChange={(event) => setDbForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="Connection name"
                className="industrial-input min-h-10"
              />
              <input
                value={dbForm.dbType}
                onChange={(event) => setDbForm((prev) => ({ ...prev, dbType: event.target.value }))}
                placeholder="DB type (postgresql)"
                className="industrial-input min-h-10"
              />
              <input
                value={dbForm.host}
                onChange={(event) => setDbForm((prev) => ({ ...prev, host: event.target.value }))}
                placeholder="Host"
                className="industrial-input min-h-10"
              />
              <input
                value={dbForm.port}
                onChange={(event) => setDbForm((prev) => ({ ...prev, port: event.target.value }))}
                placeholder="Port"
                className="industrial-input min-h-10"
              />
              <input
                value={dbForm.database}
                onChange={(event) =>
                  setDbForm((prev) => ({ ...prev, database: event.target.value }))
                }
                placeholder="Database name"
                className="industrial-input min-h-10"
              />
              <input
                value={dbForm.username}
                onChange={(event) =>
                  setDbForm((prev) => ({ ...prev, username: event.target.value }))
                }
                placeholder="Username"
                className="industrial-input min-h-10"
              />
              <input
                type="password"
                value={dbForm.password}
                onChange={(event) =>
                  setDbForm((prev) => ({ ...prev, password: event.target.value }))
                }
                placeholder="Password"
                className="industrial-input min-h-10"
              />
              <button
                type="button"
                onClick={addDbConnection}
                className="btn-industrial-primary min-h-10 px-4 text-xs"
              >
                Save Connection
              </button>
            </div>
          ) : null}

          {dbSources.length === 0 ? (
            <p className="rounded-xl border border-dashed border-[#adb7c4] p-6 text-sm text-foreground-muted">
              No database connections yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {dbSources.map((source) => (
                <li
                  key={source.id}
                  className="industrial-card flex items-center justify-between p-4"
                >
                  <div>
                    <p className="text-sm font-semibold">{source.name}</p>
                    <p className="font-mono text-xs text-foreground-muted">
                      {source.host}:{source.port}
                      {source.database ? ` • ${source.database}` : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSource(source.id)}
                    className="rounded-md px-3 py-1.5 text-xs font-bold uppercase tracking-[0.05em] text-accent transition hover:bg-[#ffd8dd]"
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
