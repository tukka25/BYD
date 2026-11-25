import { stat } from "@/components/numbers";
import { Section } from "@/components/section";

export function HowItWorks() {
  const steps = [
    { name: "Analyst", text: "Reads a profile of every table, from its values alone, and proposes what to show." },
    { name: "Planner", text: "Writes every chart's plan in one call: kind, table, columns, aggregation and title." },
    {
      name: "Plan checks",
      text: `Test every column against the real tables. Problems go back in plain words, up to ${stat("plan_tries")} tries.`,
    },
    { name: "Chartist", text: "The fine-tuned model writes the Plotly code for each plan." },
    { name: "Sandbox", text: "Runs the code on the data. Code that fails goes back to the model." },
    {
      name: "Drawing check",
      text: `Lines that run back and forth and bars that stack raw rows go back too. A chart gets at most ${stat("max_repairs")} fixes.`,
    },
  ];
  return (
    <Section id="how" kicker="How the app works" title="Every chart is the model's own code">
      <ol className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
        {steps.map((step, index) => (
          <li key={step.name} className="rounded-[var(--r-card)] bg-surface p-4 shadow-[var(--lift-1)]">
            <p className="font-mono text-[11.5px] text-pine tabular">{String(index + 1).padStart(2, "0")}</p>
            <h3 className="mt-2 font-display text-[16px] font-semibold leading-snug">{step.name}</h3>
            <p className="mt-1.5 text-[13.5px] leading-relaxed">{step.text}</p>
          </li>
        ))}
      </ol>
      <p className="mt-4 rounded-[var(--r-card)] bg-pine-wash px-5 py-4 text-[14px] leading-relaxed text-ink">
        <strong>No hardcoded charts.</strong> A chart the model cannot draw after {stat("max_repairs")} fixes is reported
        as failed, never replaced by a template.
      </p>
      <p className="mt-3 text-[13px] text-muted">
        A single chart asked for in plain words takes the same path, with a detective to pick its table and a narrator to
        title it.
      </p>
    </Section>
  );
}
