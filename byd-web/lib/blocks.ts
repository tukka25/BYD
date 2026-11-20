import { authorizedFetch } from "@/lib/backend";

export type BlockKind = "chart" | "metric" | "text";

export interface Block {
  id: string;
  kind: BlockKind;
  title: string;
  prompt?: string | null;
  code?: string | null;
  figure?: Record<string, unknown> | null;
  text_body?: string | null;
  source_name?: string | null;
  chart_type?: string | null;
  used_fallback: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
}

export async function listBlocks(token: string, reportId: string): Promise<Block[]> {
  return authorizedFetch<Block[]>(`/api/v1/dashboard/${reportId}/blocks`, token);
}

/* Generation runs the whole agent workflow and takes 13-15s, so callers must
   treat this as a long operation and show the wait honestly. */
export async function generateBlock(
  token: string,
  reportId: string,
  input: { prompt: string; dataSource?: string },
): Promise<Block> {
  return authorizedFetch<Block>(`/api/v1/dashboard/${reportId}/blocks/generate`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: input.prompt, data_source: input.dataSource ?? null }),
  });
}

export async function createBlock(
  token: string,
  reportId: string,
  input: { kind: "text" | "metric"; title?: string; text_body?: string },
): Promise<Block> {
  return authorizedFetch<Block>(`/api/v1/dashboard/${reportId}/blocks`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind: input.kind,
      title: input.title ?? "",
      text_body: input.text_body ?? "",
    }),
  });
}

export async function updateBlock(
  token: string,
  reportId: string,
  blockId: string,
  patch: Partial<Pick<Block, "title" | "text_body" | "x" | "y" | "w" | "h">>,
): Promise<Block> {
  return authorizedFetch<Block>(`/api/v1/dashboard/${reportId}/blocks/${blockId}`, token, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

/* One write for a whole drag, rather than a request per block. */
export async function saveLayout(
  token: string,
  reportId: string,
  items: Array<{ id: string; x: number; y: number; w: number; h: number }>,
): Promise<Block[]> {
  return authorizedFetch<Block[]>(`/api/v1/dashboard/${reportId}/blocks/layout`, token, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(items),
  });
}

export async function deleteBlock(token: string, reportId: string, blockId: string): Promise<void> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1/dashboard/${reportId}/blocks/${blockId}`,
    { method: "DELETE", headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok && response.status !== 204) {
    throw new Error(`Could not delete the block (${response.status})`);
  }
}
