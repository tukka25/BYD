import { authorizedFetch, backendBaseUrl } from "@/lib/backend";

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

/* --- generating a whole dashboard --------------------------------------
   Five or six chart generations end to end is a minute and a half, so the
   server streams: each block is reported the moment it exists and the
   progress shown is a real count rather than a timer pretending to be one.

   Server-sent events over POST, so `EventSource` is out (it is GET only) and
   the body is parsed here. */

/** Where a planned block will land, known before it has been built. */
export interface PlannedSection {
  index: number;
  kind: "chart" | "text";
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardProgress {
  onPlan?: (plan: {
    total: number;
    source: string;
    brief: string;
    sections: PlannedSection[];
  }) => void;
  onStep?: (step: { index: number; total: number; label: string }) => void;
  onBlock?: (block: Block) => void;
  onSkipped?: (skip: { index: number; label: string; reason: string }) => void;
}

export async function generateDashboard(
  token: string,
  reportId: string,
  brief: string,
  handlers: DashboardProgress,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${backendBaseUrl()}/api/v1/dashboard/${reportId}/blocks/dashboard`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ brief }),
      signal,
    },
  );

  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `Could not plan this dashboard (${response.status})`);
  }
  if (!response.body) throw new Error("The server sent no dashboard stream.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (event: string, data: string) => {
    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      return;
    }
    if (event === "plan") handlers.onPlan?.(payload as never);
    else if (event === "step") handlers.onStep?.(payload as never);
    else if (event === "block") handlers.onBlock?.(payload as Block);
    else if (event === "skipped") handlers.onSkipped?.(payload as never);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // An event ends at a blank line; anything after it is the next one, which
    // may still be arriving.
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
      if (data) dispatch(event, data);
      split = buffer.indexOf("\n\n");
    }
  }
}
