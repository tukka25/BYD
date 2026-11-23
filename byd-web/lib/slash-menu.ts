/* The "/" menu's logic, kept free of React and of imports so Node's own test
   runner loads it directly (`npm test`). */

export interface KindOption {
  kind: string;
  label: string;
  best_for: string;
  needs: string;
  aliases: string[];
}

export interface SlashToken {
  query: string;
  start: number;
  end: number;
}

/** The "/word" being typed at the caret: a "/" at the start or after a space. */
export function slashTokenAt(text: string, caret: number): SlashToken | null {
  const before = text.slice(0, caret);
  const match = /(^|\s)\/([\w-]*)$/.exec(before);
  if (!match) return null;
  return { query: match[2], start: caret - match[2].length - 1, end: caret };
}

/** Kinds matching the query: names that start with it, then words or aliases
    that do, then any that contain it. */
export function filterKinds(options: KindOption[], query: string): KindOption[] {
  const q = query.trim().toLowerCase();
  if (!q) return options;
  const rank = (option: KindOption): number => {
    const label = option.label.toLowerCase();
    if (option.kind.startsWith(q) || label.startsWith(q)) return 0;
    const words = [...label.split(/\s+/), ...option.aliases.map((alias) => alias.toLowerCase())];
    if (words.some((word) => word.startsWith(q))) return 1;
    if ([option.kind, ...words].some((word) => word.includes(q))) return 2;
    return -1;
  };
  return options
    .map((option) => ({ option, score: rank(option) }))
    .filter((entry) => entry.score >= 0)
    .sort((a, b) => a.score - b.score)
    .map((entry) => entry.option);
}

/** The text without the typed "/word", and where the caret goes. */
export function removeToken(text: string, token: SlashToken): { text: string; caret: number } {
  const head = text.slice(0, token.start);
  const tail = text.slice(token.end).replace(/^ /, "");
  return { text: head + tail, caret: token.start };
}
