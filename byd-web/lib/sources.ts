import { authorizedFetch, backendBaseUrl } from "@/lib/backend";

export interface Source {
  id: string;
  source_type: "file" | "db";
  display_name: string;
  original_filename?: string | null;
  file_extension?: string | null;
  file_size_bytes?: number | null;
  status?: string | null;
  created_at: string;

  db_type?: string | null;
  db_host?: string | null;
  db_port?: number | null;
  db_name?: string | null;
  db_username?: string | null;
}

/** A database this server can actually reach — `available` is the driver. */
export interface DatabaseKind {
  id: string;
  label: string;
  default_port: number;
  available: boolean;
}

export interface ConnectionInput {
  display_name: string;
  db_type: string;
  db_host: string;
  db_port: number;
  db_name: string;
  db_username: string;
  db_password: string;
}

export interface ProbeResult {
  ok: boolean;
  error: string | null;
  tables: string[];
  table_count?: number;
}

export async function listDatabaseKinds(token: string): Promise<DatabaseKind[]> {
  return authorizedFetch<DatabaseKind[]>("/api/v1/data-sources/database-kinds", token);
}

/** Connects for real and reports what is there, without storing anything. */
export async function testConnection(
  token: string,
  input: ConnectionInput,
): Promise<ProbeResult> {
  return authorizedFetch<ProbeResult>("/api/v1/data-sources/db-connection/test", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/** The backend connects before it stores, so this fails loudly on bad details. */
export async function createConnection(token: string, input: ConnectionInput): Promise<Source> {
  return authorizedFetch<Source>("/api/v1/data-sources/db-connection", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/** The tables behind a database source; empty for a file. */
export async function listTables(token: string, id: string): Promise<string[]> {
  return authorizedFetch<string[]>(`/api/v1/data-sources/${id}/tables`, token);
}

export function sourceSubtitle(source: Source): string {
  if (source.source_type === "db") {
    const where = [source.db_host, source.db_port].filter(Boolean).join(":");
    return [source.db_name, where].filter(Boolean).join(" · ");
  }
  return formatSize(source.file_size_bytes);
}

export const ALLOWED_EXTENSIONS = [".csv", ".xls", ".xlsx"];

export function formatSize(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export async function listSources(token: string): Promise<Source[]> {
  return authorizedFetch<Source[]>("/api/v1/data-sources", token);
}

export async function uploadSource(token: string, file: File, displayName?: string): Promise<Source> {
  const body = new FormData();
  body.append("file", file);
  if (displayName) body.append("display_name", displayName);

  // Not authorizedFetch: that sets a JSON content type, and multipart needs the
  // browser to set its own boundary.
  const response = await fetch(`${backendBaseUrl()}/api/v1/data-sources/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body,
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `Upload failed (${response.status})`);
  }
  return (await response.json()) as Source;
}

export async function deleteSource(token: string, id: string): Promise<void> {
  const response = await fetch(`${backendBaseUrl()}/api/v1/data-sources/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok && response.status !== 204) {
    throw new Error(`Could not remove that source (${response.status})`);
  }
}
