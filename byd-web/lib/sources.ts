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
