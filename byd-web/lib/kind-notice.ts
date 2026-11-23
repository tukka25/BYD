/* The line the canvas shows when a chart kind the user picked for a dashboard
   is not in the plan. Kept free of imports so Node's own test runner loads it
   directly (`npm test`); the caller passes the kinds list in. */

export interface KindLabel {
  kind: string;
  label: string;
}

function named(kind: string, kinds: KindLabel[]): string {
  const label = kinds.find((k) => k.kind === kind)?.label ?? kind;
  // "Pie chart" reads "a pie chart"; an acronym keeps its capitals ("a KPI card").
  const text = /^[A-Z][a-z]/.test(label) ? label[0].toLowerCase() + label.slice(1) : label;
  return `${/^[aeiou]/i.test(text) ? "an" : "a"} ${text}`;
}

/** "Could not plan a pie chart for this data." for the kinds the plan lacks; "" when it lacks none. */
export function missingKindsNotice(missing: string[], kinds: KindLabel[]): string {
  if (missing.length === 0) return "";
  const names = missing.map((kind) => named(kind, kinds));
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
  return `Could not plan ${list} for this data.`;
}
