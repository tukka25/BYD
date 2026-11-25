import journey from "@/data/journey.json";
import { Section } from "@/components/section";
import { commitUrl } from "@/lib/site";

type Milestone = { date: string; commit: string; subject: string; title: string; text: string };

export function Journey() {
  return (
    <Section id="journey" kicker="Journey" title="From a first commit to a fine-tuned chartist">
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(journey as Milestone[]).map((milestone) => (
          <li key={milestone.commit} className="rounded-[var(--r-card)] bg-surface p-4 shadow-[var(--lift-1)]">
            <p className="font-mono text-[11.5px] text-muted tabular">{milestone.date}</p>
            <h3 className="mt-2 font-display text-[16px] font-semibold leading-snug">{milestone.title}</h3>
            <p className="mt-1.5 text-[13.5px] leading-relaxed">{milestone.text}</p>
            <a
              href={commitUrl(milestone.commit)}
              className="mt-3 inline-block font-mono text-[11.5px] text-pine underline decoration-pine/30 underline-offset-2"
            >
              {milestone.commit}
            </a>
          </li>
        ))}
      </ol>
    </Section>
  );
}
