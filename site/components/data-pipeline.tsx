import { stat } from "@/components/numbers";
import { Section } from "@/components/section";

export function DataPipeline() {
  const steps = [
    {
      title: "Schemas and questions",
      text: `Claude Haiku wrote ${stat("schemas")} business table schemas, each with a real CSV, and ${stat("questions")} questions a person might ask of them.`,
    },
    {
      title: "Code answers",
      text: `Claude Sonnet wrote a Plotly answer for each of ${stat("targets_attempted")} training questions.`,
    },
    {
      title: "Kept only if it renders",
      text: `Every answer ran in the app's own sandbox against its CSV. ${stat("targets_kept")} rendered and were kept.`,
    },
    {
      title: "A frozen test set",
      text: `${stat("test_questions")} questions on ${stat("test_schemas")} schemas never seen in training, frozen before the first training run.`,
    },
    {
      title: "Two training sets",
      text: `lora-v1: ${stat("v1_train_rows")} rows, ${stat("v1_synthetic_rows")} from this pipeline and ${stat("v1_docs_rows")} docs examples rewritten to the app's contract. lora-v2: ${stat("v2_train_rows")}, adding analyst and planner examples distilled from Claude Opus 5.5.`,
    },
  ];
  return (
    <Section id="data" kicker="The data" title="Training data the app's own sandbox approved">
      <ol className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
        {steps.map((step, index) => (
          <li key={step.title} className="rounded-[var(--r-card)] bg-surface p-4 shadow-[var(--lift-1)]">
            <p className="font-mono text-[11.5px] text-pine tabular">{String(index + 1).padStart(2, "0")}</p>
            <h3 className="mt-2 font-display text-[16px] font-semibold leading-snug">{step.title}</h3>
            <p className="mt-1.5 text-[13.5px] leading-relaxed">{step.text}</p>
          </li>
        ))}
      </ol>
      <p className="mt-4 text-[13px] text-muted">
        The Claude API cost of the data: {stat("v1_data_cost", 2)} for lora-v1, {stat("v2_data_cost")} for lora-v2.
      </p>
    </Section>
  );
}
