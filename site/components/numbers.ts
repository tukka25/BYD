import stats from "@/data/stats.json";
import { findStat, formatStat, type Stat } from "@/lib/stats";

const ALL = stats as unknown as Stat[];

/** A number from data/stats.json as the page shows it; `decimals` shows fewer places. */
export function stat(id: string, decimals?: number): string {
  return formatStat(findStat(ALL, id), decimals);
}

/** The repository file a number came from, for a link beside it. A sum has none of its own. */
export function statSource(id: string): string | null {
  const source = findStat(ALL, id).source;
  return source.kind === "sum" ? null : source.file;
}

/** What a number measures, for the title of its link. */
export function statLabel(id: string): string {
  return findStat(ALL, id).label;
}
