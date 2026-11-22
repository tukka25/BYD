import { authorizedFetch, backendBaseUrl, streamEvents } from "@/lib/backend";

/* The same chart question, put to the local fine-tuned model and to Claude
   Opus 5.5 on the same harness. Nothing is stored: what comes back is the
   evidence, and it lives for as long as the page is open. */

export type Engine = "slm" | "opus";

export interface EngineInfo {
  id: Engine;
  label: string;
  available: boolean;
}

export interface CellResult {
  engine: Engine;
  index: number;
  ok: boolean;
  code: string;
  figure: Record<string, unknown> | null;
  error: string | null;
  repairs: number;
  violations: string[];
  seconds: number;
  input_tokens: number;
  output_tokens: number;
}

export interface PlannedChart {
  index: number;
  question: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ComparisonPlan {
  source: string;
  rows: number;
  columns: string[];
  questions: string[];
  /** Composed from the data profile, not by a model: the same on both sides. */
  intro: string;
  intro_title: string;
  sections: PlannedChart[];
  engines: Array<{ id: Engine; label: string }>;
}

export interface ComparisonHandlers {
  onPlan?: (plan: ComparisonPlan) => void;
  onQuestion?: (q: { index: number; question: string; plan: Record<string, unknown> }) => void;
  onCell?: (cell: CellResult) => void;
}

export async function listEngines(token: string): Promise<EngineInfo[]> {
  return authorizedFetch<EngineInfo[]>("/api/v1/comparison/engines", token);
}

export async function runComparison(
  token: string,
  input: { sourceId: string; table?: string; brief: string },
  handlers: ComparisonHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${backendBaseUrl()}/api/v1/comparison/run`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      source_id: input.sourceId,
      table: input.table ?? null,
      brief: input.brief,
    }),
    signal,
  });

  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `Could not run the comparison (${response.status})`);
  }

  await streamEvents(response, (event, data) => {
    if (event === "plan") handlers.onPlan?.(data as ComparisonPlan);
    else if (event === "question") handlers.onQuestion?.(data as never);
    else if (event === "cell") handlers.onCell?.(data as CellResult);
  });
}

/* Published rates for claude-opus-5-5. Shown so the cost of a run is a number
   on screen rather than something the user finds out on their bill. Thinking
   is billed as output, which is most of it. */
const OPUS_INPUT_PER_MTOK = 4;
const OPUS_OUTPUT_PER_MTOK = 20;

export function opusCost(cells: CellResult[]): number {
  return cells
    .filter((c) => c.engine === "opus")
    .reduce(
      (total, c) =>
        total +
        (c.input_tokens / 1_000_000) * OPUS_INPUT_PER_MTOK +
        (c.output_tokens / 1_000_000) * OPUS_OUTPUT_PER_MTOK,
      0,
    );
}
