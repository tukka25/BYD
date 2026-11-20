import { authorizedFetch, backendBaseUrl } from "@/lib/backend";

/* Reports are the backend's `dashboards`. The name differs because "dashboard"
   already means the whole product to a user; what they create is a report. */

export interface Report {
  id: string;
  title: string;
  description: string | null;
  dataSourceIds: string[];
  createdAt: string;
  updatedAt: string;
}

interface BackendDashboard {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  data_source_ids: string[];
  created_at: string;
  updated_at: string;
}

function toReport(d: BackendDashboard): Report {
  return {
    id: d.id,
    title: d.title,
    description: d.description,
    dataSourceIds: d.data_source_ids ?? [],
    createdAt: d.created_at,
    updatedAt: d.updated_at,
  };
}

export async function listReports(token: string): Promise<Report[]> {
  const rows = await authorizedFetch<BackendDashboard[]>("/api/v1/dashboard", token);
  return rows.map(toReport);
}

export async function getReport(token: string, id: string): Promise<Report> {
  return toReport(await authorizedFetch<BackendDashboard>(`/api/v1/dashboard/${id}`, token));
}

/* The sidebar lists reports and the canvas can rename one, so a rename has to
   reach a component that did not make the request. Same shape as the session
   store: a window event, rather than threading a callback through the shell. */
const REPORTS_EVENT = "promptdash:reports";

export function announceReportsChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(REPORTS_EVENT));
}

export function subscribeToReports(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(REPORTS_EVENT, onChange);
  return () => window.removeEventListener(REPORTS_EVENT, onChange);
}

export async function updateReport(
  token: string,
  id: string,
  input: { title?: string; description?: string | null; dataSourceIds?: string[] },
): Promise<Report> {
  const report = toReport(
    await authorizedFetch<BackendDashboard>(`/api/v1/dashboard/${id}`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: input.title,
        description: input.description,
        data_source_ids: input.dataSourceIds,
      }),
    }),
  );
  announceReportsChanged();
  return report;
}

export async function createReport(
  token: string,
  input: { title: string; description?: string; dataSourceIds?: string[] },
): Promise<Report> {
  return toReport(
    await authorizedFetch<BackendDashboard>("/api/v1/dashboard", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: input.title,
        description: input.description ?? null,
        data_source_ids: input.dataSourceIds ?? [],
      }),
    }),
  );
}

/* --- health --------------------------------------------------------------
   Read so the interface can state which model is serving and that it is local.
   The claim is the product; showing it beats asserting it in copy. */

export interface LocalHealth {
  status: string;
  llm_backend: string;
  model: string;
  llm_url: string;
  upload_dir: string;
  uploads_present: string[];
  insecure_dev_secrets: boolean;
}

export async function fetchHealth(): Promise<LocalHealth | null> {
  try {
    const response = await fetch(`${backendBaseUrl()}/health`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as LocalHealth;
  } catch {
    return null;
  }
}
