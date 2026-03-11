export interface DataSource {
  id: string;
  name: string;
  type: "file" | "db";
  createdAt: string;
  sizeLabel?: string;
  extension?: string;
  status?: "connected" | "disconnected";
  host?: string;
  port?: string;
  database?: string;
}

const defaultSources: DataSource[] = [
  {
    id: "seed-sales-csv",
    name: "sales_q1_2024.csv",
    type: "file",
    createdAt: new Date().toISOString(),
    sizeLabel: "1.2 MB",
    extension: "csv",
  },
  {
    id: "seed-customer-xlsx",
    name: "customer_churn.xlsx",
    type: "file",
    createdAt: new Date().toISOString(),
    sizeLabel: "450 KB",
    extension: "xlsx",
  },
  {
    id: "seed-db-local",
    name: "Local PostgreSQL",
    type: "db",
    createdAt: new Date().toISOString(),
    status: "connected",
    host: "localhost",
    port: "5432",
    database: "analytics",
  },
];

export function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function dataSourcesKey(userId: string): string {
  return `promptdash_data_sources_${userId}`;
}

function selectedSourcesKey(userId: string): string {
  return `promptdash_selected_sources_${userId}`;
}

export function loadDataSources(userId: string): DataSource[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(dataSourcesKey(userId));
  if (!raw) {
    window.localStorage.setItem(dataSourcesKey(userId), JSON.stringify(defaultSources));
    return defaultSources;
  }

  try {
    const parsed = JSON.parse(raw) as DataSource[];
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch {
    return [];
  }
}

export function saveDataSources(userId: string, sources: DataSource[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(dataSourcesKey(userId), JSON.stringify(sources));
}

export function loadSelectedSourceIds(userId: string): string[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(selectedSourcesKey(userId));
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw) as string[];
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch {
    return [];
  }
}

export function saveSelectedSourceIds(userId: string, ids: string[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(selectedSourcesKey(userId), JSON.stringify(ids));
}

export function bytesToSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}
