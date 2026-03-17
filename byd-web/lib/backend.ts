import { AuthUser } from "@/lib/auth";
import { DataSource } from "@/lib/data-sources";

export function backendBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export interface BackendDataSource {
  id: string;
  source_type: "file" | "db";
  display_name: string;
  created_at: string;
  file_extension?: string | null;
  file_size_bytes?: number | null;
  db_host?: string | null;
  db_port?: number | null;
  db_name?: string | null;
  status?: string | null;
}

export function mapBackendDataSource(source: BackendDataSource): DataSource {
  return {
    id: source.id,
    name: source.display_name,
    type: source.source_type,
    createdAt: source.created_at,
    extension: source.file_extension ?? undefined,
    sizeLabel:
      source.file_size_bytes && source.file_size_bytes > 0
        ? `${Math.round(source.file_size_bytes / 1024)} KB`
        : undefined,
    host: source.db_host ?? undefined,
    port: source.db_port ? String(source.db_port) : undefined,
    database: source.db_name ?? undefined,
    status: source.status === "active" ? "connected" : "disconnected",
  };
}

export async function authorizedFetch<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${backendBaseUrl()}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function fetchCurrentUser(token: string): Promise<AuthUser> {
  const me = await authorizedFetch<{ id: string; email: string; full_name: string }>(
    "/api/v1/auth/me",
    token,
  );
  return { id: me.id, email: me.email, name: me.full_name };
}

