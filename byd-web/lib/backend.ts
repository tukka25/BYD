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

  if (response.status === 401) {
    // The token no longer identifies anyone: expired, or issued against a
    // different database. Either way the only recovery is signing in again, so
    // do that rather than surfacing the backend's "User not found".
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("promptdash_session_user");
      window.localStorage.removeItem("promptdash_access_token");
      window.location.href = "/login";
    }
    throw new Error("Your session has expired. Sign in again.");
  }

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



/* --- server-sent events ------------------------------------------------
   Both the dashboard build and the model comparison stream over POST, so
   `EventSource` is out (it is GET only) and the body is parsed here. */

export async function streamEvents(
  response: Response,
  dispatch: (event: string, data: unknown) => void,
): Promise<void> {
  if (!response.body) throw new Error("The server sent no stream.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // An event ends at a blank line; what follows may still be arriving.
    let split = buffer.indexOf("\n\n");
    while (split !== -1) {
      const chunk = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      let event = "message";
      let data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) {
        try {
          dispatch(event, JSON.parse(data));
        } catch {
          // A half-written event is not worth failing the stream over.
        }
      }
      split = buffer.indexOf("\n\n");
    }
  }
}
