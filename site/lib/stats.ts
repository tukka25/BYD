/* Every number on the page, formatted from the raw value its source recorded.
   The entries live in data/stats.json, and tests/stats.test.mts reads each one
   back from its source. Import-free, so Node's test runner can load it. */

export type StatFormat = { kind: "percent" | "usd" | "number"; decimals: number } | { kind: "duration" };

export type StatSource =
  | { kind: "json"; file: string; path: (string | number)[] }
  | { kind: "quote"; file: string; quote: string }
  | { kind: "sum"; of: string[] };

export type Stat = { id: string; value: number; format: StatFormat; label: string; source: StatSource };

function grouped(value: number, decimals: number): string {
  return value.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** The value as the page shows it. `decimals` shows fewer places: 94% from 0.9433. */
export function formatStat(stat: Pick<Stat, "value" | "format">, decimals?: number): string {
  const { value, format } = stat;
  if (format.kind === "duration") {
    const hours = Math.floor(value / 3600);
    const minutes = Math.round((value - hours * 3600) / 60);
    return `${hours} h ${minutes} m`;
  }
  const places = decimals ?? format.decimals;
  if (format.kind === "percent") return `${(value * 100).toFixed(places)}%`;
  if (format.kind === "usd") return `$${grouped(value, places)}`;
  return grouped(value, places);
}

/** The entry with this id. Throws, so a missing number fails the build instead of printing nothing. */
export function findStat(stats: readonly Stat[], id: string): Stat {
  const found = stats.find((stat) => stat.id === id);
  if (!found) throw new Error(`no stat with id ${id} in data/stats.json`);
  return found;
}
