"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Check,
  Database,
  FileSpreadsheet,
  Loader2,
  Plug,
  ShieldAlert,
  Table2,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { Button, Chip, Field, IconButton, Panel, inputClass } from "@/components/ui";
import { fetchHealth } from "@/lib/reports";
import {
  ALLOWED_EXTENSIONS,
  createConnection,
  listDatabaseKinds,
  listSources,
  sourceSubtitle,
  testConnection,
  uploadSource,
  deleteSource,
  type ConnectionInput,
  type DatabaseKind,
  type ProbeResult,
  type Source,
} from "@/lib/sources";

/* Where data comes from, in one place. The same component is used on the data
   page and from a report's source chip, because "add a connection" should not
   be a different thing depending on which screen you happened to open. */

const selectClass = `${inputClass} appearance-none bg-[length:12px] bg-[right_0.9rem_center] bg-no-repeat pr-10`;

const CHEVRON =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8' fill='none' stroke='%235e5e6b' stroke-width='2' stroke-linecap='round'%3E%3Cpath d='M1 1l5 5 5-5'/%3E%3C/svg%3E\")";

function SourceIcon({ source }: { source: Source }) {
  const Icon = source.source_type === "db" ? Database : FileSpreadsheet;
  return <Icon size={16} strokeWidth={2.25} className="shrink-0 text-muted" />;
}

export function SourceRow({
  source,
  selected,
  onToggle,
  onDelete,
}: {
  source: Source;
  selected?: boolean;
  onToggle?: () => void;
  onDelete?: () => void;
}) {
  const subtitle = sourceSubtitle(source);
  const body = (
    <>
      {onToggle ? (
        <span
          className={[
            "grid size-5 shrink-0 place-items-center rounded-[6px]",
            selected ? "bg-violet text-white" : "bg-surface ring-1 ring-inset ring-hairline-strong",
          ].join(" ")}
        >
          {selected ? <Check size={13} strokeWidth={3} /> : null}
        </span>
      ) : null}
      <SourceIcon source={source} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-semibold text-ink">
          {source.display_name}
        </span>
        {subtitle ? (
          <span className="block truncate text-[12px] text-muted">{subtitle}</span>
        ) : null}
      </span>
      {source.source_type === "db" ? <Chip tone="violet">Database</Chip> : null}
    </>
  );

  return (
    <li className="flex items-center gap-2">
      {onToggle ? (
        <button
          onClick={onToggle}
          aria-pressed={selected}
          className={[
            "flex min-w-0 flex-1 items-center gap-3 rounded-[var(--r-card)] px-3.5 py-3 text-left",
            "transition-colors duration-150 ease-[var(--ease-out)]",
            selected ? "bg-violet-wash ring-1 ring-inset ring-violet" : "bg-sunken hover:bg-[#e0e0e7]",
          ].join(" ")}
        >
          {body}
        </button>
      ) : (
        <div className="flex min-w-0 flex-1 items-center gap-3 rounded-[var(--r-card)] bg-sunken px-3.5 py-3">
          {body}
        </div>
      )}
      {onDelete ? (
        <IconButton label={`Remove ${source.display_name}`} tone="danger" onClick={onDelete}>
          <Trash2 size={15} strokeWidth={2.25} />
        </IconButton>
      ) : null}
    </li>
  );
}

/* --- connecting a database ---------------------------------------------- */

function emptyConnection(kind?: DatabaseKind): ConnectionInput {
  return {
    display_name: "",
    db_type: kind?.id ?? "postgresql",
    db_host: "",
    db_port: kind?.default_port ?? 5432,
    db_name: "",
    db_username: "",
    db_password: "",
  };
}

export function ConnectDatabase({
  token,
  onConnected,
  onCancel,
}: {
  token: string;
  onConnected: (source: Source) => void;
  onCancel: () => void;
}) {
  const [kinds, setKinds] = useState<DatabaseKind[]>([]);
  const [form, setForm] = useState<ConnectionInput>(emptyConnection());
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [busy, setBusy] = useState<"idle" | "testing" | "saving">("idle");
  const [error, setError] = useState<string | null>(null);
  const [insecure, setInsecure] = useState(false);

  useEffect(() => {
    listDatabaseKinds(token)
      .then((rows) => {
        setKinds(rows);
        const first = rows.find((k) => k.available) ?? rows[0];
        if (first) setForm((current) => ({ ...current, db_type: first.id, db_port: first.default_port }));
      })
      .catch(() => setKinds([]));
    fetchHealth().then((health) => setInsecure(Boolean(health?.insecure_dev_secrets)));
  }, [token]);

  function set<K extends keyof ConnectionInput>(key: K, value: ConnectionInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setProbe(null);
  }

  function pickKind(id: string) {
    const kind = kinds.find((k) => k.id === id);
    setForm((current) => ({ ...current, db_type: id, db_port: kind?.default_port ?? current.db_port }));
    setProbe(null);
  }

  const complete =
    form.display_name.trim().length > 1 &&
    form.db_host.trim() &&
    form.db_name.trim() &&
    form.db_username.trim() &&
    form.db_password;

  async function test() {
    setBusy("testing");
    setError(null);
    try {
      setProbe(await testConnection(token, form));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the server.");
    } finally {
      setBusy("idle");
    }
  }

  async function connect() {
    setBusy("saving");
    setError(null);
    try {
      onConnected(await createConnection(token, form));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that connection.");
    } finally {
      setBusy("idle");
    }
  }

  return (
    <div className="rounded-[var(--r-card)] bg-sunken p-4">
      <div className="mb-3 flex items-center gap-2">
        <Plug size={15} strokeWidth={2.25} className="text-violet" />
        <h3 className="text-[13.5px] font-bold text-ink">Connect a database</h3>
      </div>

      {insecure ? (
        <div className="mb-3 flex items-start gap-2 rounded-[var(--r-control)] bg-amber-wash px-3 py-2.5 text-[12.5px] text-[#8a5a00]">
          <ShieldAlert size={14} strokeWidth={2.25} className="mt-px shrink-0" />
          <span>
            This server is still using the placeholder encryption key committed to the repository,
            so a stored password could be read by anyone with a copy of it. Run{" "}
            <span className="font-mono">make secrets</span> before connecting anything real.
          </span>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Name" hint="What this connection is called in your source list." htmlFor="conn-name">
            <input
              id="conn-name"
              autoFocus
              value={form.display_name}
              onChange={(event) => set("display_name", event.target.value)}
              placeholder="Production Postgres"
              className={inputClass}
            />
          </Field>
        </div>

        <Field label="Database" htmlFor="conn-kind">
          <select
            id="conn-kind"
            value={form.db_type}
            onChange={(event) => pickKind(event.target.value)}
            className={selectClass}
            style={{ backgroundImage: CHEVRON }}
          >
            {kinds.map((kind) => (
              <option key={kind.id} value={kind.id} disabled={!kind.available}>
                {kind.label}
                {kind.available ? "" : " — driver not installed"}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Port" htmlFor="conn-port">
          <input
            id="conn-port"
            type="number"
            min={1}
            max={65535}
            value={form.db_port}
            onChange={(event) => set("db_port", Number(event.target.value) || 0)}
            className={`${inputClass} tabular`}
          />
        </Field>

        <Field label="Host" htmlFor="conn-host">
          <input
            id="conn-host"
            value={form.db_host}
            onChange={(event) => set("db_host", event.target.value)}
            placeholder="db.example.com"
            className={inputClass}
          />
        </Field>

        <Field label="Database name" htmlFor="conn-db">
          <input
            id="conn-db"
            value={form.db_name}
            onChange={(event) => set("db_name", event.target.value)}
            placeholder="analytics"
            className={inputClass}
          />
        </Field>

        <Field label="User" htmlFor="conn-user">
          <input
            id="conn-user"
            value={form.db_username}
            onChange={(event) => set("db_username", event.target.value)}
            autoComplete="off"
            className={inputClass}
          />
        </Field>

        <Field label="Password" htmlFor="conn-password">
          <input
            id="conn-password"
            type="password"
            value={form.db_password}
            onChange={(event) => set("db_password", event.target.value)}
            autoComplete="new-password"
            className={inputClass}
          />
        </Field>
      </div>

      {probe ? (
        probe.ok ? (
          <div className="mt-3 rounded-[var(--r-control)] bg-teal-wash px-3 py-2.5 text-[12.5px] text-[#0a6b60]">
            <div className="flex items-center gap-2 font-semibold">
              <Check size={14} strokeWidth={3} />
              Connected. {probe.table_count ?? probe.tables.length} table
              {(probe.table_count ?? probe.tables.length) === 1 ? "" : "s"} found.
            </div>
            {probe.tables.length > 0 ? (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {probe.tables.slice(0, 8).map((table) => (
                  <span
                    key={table}
                    className="inline-flex items-center gap-1 rounded-[var(--r-pill)] bg-surface px-2 py-0.5 font-mono text-[11px] text-body"
                  >
                    <Table2 size={11} strokeWidth={2.25} />
                    {table}
                  </span>
                ))}
                {probe.tables.length > 8 ? (
                  <span className="text-[11px] text-muted">+{probe.tables.length - 8} more</span>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="mt-3 flex items-start gap-2 rounded-[var(--r-control)] bg-coral-wash px-3 py-2.5 text-[12.5px] text-[#b5301c]">
            <AlertTriangle size={14} strokeWidth={2.25} className="mt-px shrink-0" />
            <span className="break-words">{probe.error}</span>
          </div>
        )
      ) : null}

      {error ? (
        <div className="mt-3 flex items-start gap-2 rounded-[var(--r-control)] bg-coral-wash px-3 py-2.5 text-[12.5px] text-[#b5301c]">
          <AlertTriangle size={14} strokeWidth={2.25} className="mt-px shrink-0" />
          <span className="break-words">{error}</span>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={test} disabled={!complete || busy !== "idle"}>
          {busy === "testing" ? <Loader2 size={15} strokeWidth={2.25} className="animate-spin" /> : null}
          {busy === "testing" ? "Testing…" : "Test connection"}
        </Button>
        <Button variant="primary" onClick={connect} disabled={!complete || busy !== "idle"}>
          {busy === "saving" ? "Connecting…" : "Connect"}
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <span className="text-[12px] text-muted">
          The connection is tested before it is saved.
        </span>
      </div>
    </div>
  );
}

/* --- the list, with whatever actions the caller wants ------------------- */

export function SourceManager({
  token,
  sources,
  onSourcesChange,
  selected,
  onToggle,
  allowDelete = false,
  emptyNote,
}: {
  token: string;
  sources: Source[];
  onSourcesChange: (next: Source[]) => void;
  selected?: string[];
  onToggle?: (id: string) => void;
  allowDelete?: boolean;
  emptyNote?: ReactNode;
}) {
  const [connecting, setConnecting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    setError(null);
    try {
      const created = await uploadSource(token, files[0]);
      onSourcesChange([created, ...sources]);
      onToggle?.(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function remove(source: Source) {
    setError(null);
    try {
      await deleteSource(token, source.id);
      onSourcesChange(sources.filter((s) => s.id !== source.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove that source.");
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => fileInput.current?.click()} disabled={uploading}>
          <Upload size={15} strokeWidth={2.25} />
          {uploading ? "Uploading…" : "Upload a file"}
        </Button>
        <Button variant="secondary" onClick={() => setConnecting((v) => !v)}>
          <Database size={15} strokeWidth={2.25} />
          Connect a database
        </Button>
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

      {connecting ? (
        <ConnectDatabase
          token={token}
          onCancel={() => setConnecting(false)}
          onConnected={(source) => {
            onSourcesChange([source, ...sources]);
            onToggle?.(source.id);
            setConnecting(false);
          }}
        />
      ) : null}

      {error ? (
        <div className="flex items-start gap-2 rounded-[var(--r-card)] bg-coral-wash px-3.5 py-2.5 text-[13px] text-[#b5301c]">
          <AlertTriangle size={15} strokeWidth={2.25} className="mt-px shrink-0" />
          <span className="flex-1">{error}</span>
        </div>
      ) : null}

      {sources.length === 0 ? (
        <p className="rounded-[var(--r-card)] bg-sunken px-4 py-3 text-[13px] text-muted">
          {emptyNote ?? "No data yet. Upload a spreadsheet or connect a database."}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sources.map((source) => (
            <SourceRow
              key={source.id}
              source={source}
              selected={selected?.includes(source.id)}
              onToggle={onToggle ? () => onToggle(source.id) : undefined}
              onDelete={allowDelete ? () => void remove(source) : undefined}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/* --- the same thing, over a report ------------------------------------- */

/* Mounted only while it is open, so the ticked set is simply its initial
   state. Keeping it mounted and syncing that set in an effect is the same
   thing with a cascading render in the middle. */
export function SourceDialog({
  token,
  selected,
  onClose,
  onSave,
}: {
  token: string;
  selected: string[];
  onClose: () => void;
  onSave: (ids: string[]) => void;
}) {
  const [sources, setSources] = useState<Source[]>([]);
  const [picked, setPicked] = useState<string[]>(selected);
  const panel = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listSources(token)
      .then(setSources)
      .catch(() => setSources([]));
  }, [token]);

  useEffect(() => {
    panel.current?.querySelector<HTMLElement>("button, input, select")?.focus();
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-[rgb(18_18_22/0.45)] p-0 sm:items-center sm:p-6"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <button aria-label="Close" onClick={onClose} className="absolute inset-0 cursor-default" />

      <Panel
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label="Data for this report"
        className="relative flex max-h-[88dvh] w-full max-w-2xl flex-col overflow-hidden shadow-[var(--lift-2)] sm:max-h-[80dvh]"
      >
        <header className="flex shrink-0 items-start justify-between gap-4 px-6 pt-5">
          <div>
            <h2 className="font-display text-[20px] font-bold text-ink">Data for this report</h2>
            <p className="mt-1 text-[13px] text-muted">
              Tick what this report may read. Leave everything unticked and it searches all of your
              sources.
            </p>
          </div>
          <IconButton label="Close" onClick={onClose}>
            <X size={17} strokeWidth={2.25} />
          </IconButton>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <SourceManager
            token={token}
            sources={sources}
            onSourcesChange={setSources}
            selected={picked}
            onToggle={(id) =>
              setPicked((current) =>
                current.includes(id) ? current.filter((s) => s !== id) : [...current, id],
              )
            }
            emptyNote="Nothing here yet. Upload a spreadsheet or connect a database and it becomes available to every report."
          />
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-hairline px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => onSave(picked)}>
            Save
          </Button>
        </footer>
      </Panel>
    </div>
  );
}
