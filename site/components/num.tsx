import { stat, statLabel, statSource } from "@/components/numbers";
import { fileUrl } from "@/lib/site";

/* A number that links to the file that recorded it; its title says what it measures. */
export function Num({ id, decimals }: { id: string; decimals?: number }) {
  const file = statSource(id);
  const text = stat(id, decimals);
  if (!file) return <span title={statLabel(id)}>{text}</span>;
  return (
    <a
      href={fileUrl(file)}
      title={statLabel(id)}
      className="underline decoration-hairline-strong decoration-dotted underline-offset-4 transition-colors hover:decoration-pine"
    >
      {text}
    </a>
  );
}
