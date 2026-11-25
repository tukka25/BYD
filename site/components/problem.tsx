import { MeterCard } from "@/components/meter-card";
import { CAPTION, Lede, MEASURE, Name, Section } from "@/components/section";

const RAN = "Code that ran and drew a chart";
const KIND = "Charts of the kind asked for";

/* The base model under its two settings. Thinking on is how it ships, scored
   on the rented GPU at 16-bit (bf16) when lora-v1 was; thinking off is its
   better setting, scored on the Mac at 4-bit like both adapters. Most of the
   gap between them is the reasoning mode, not missing skill, so the copy says
   so rather than let the fine-tune take credit for the whole jump. */
export function Problem() {
  return (
    <Section id="problem" title="The problem">
      <div className="space-y-5">
        <Lede>
          Analysing sensitive or classified data with a cloud-hosted model, such as Claude or GPT, means sending that
          data off your machine to someone else&apos;s servers.
        </Lede>
        <Lede>
          I wanted to know whether a small model that runs locally could do the analysis instead. As it ships,{" "}
          <Name>Qwen3.5-9B</Name> could not.
        </Lede>
      </div>
      <div className="mt-8 grid max-w-3xl gap-3 md:grid-cols-2">
        <MeterCard
          title="Thinking on, as it ships"
          note="16-bit weights, on a rented GPU"
          meters={[
            { label: RAN, id: "base_render_pod" },
            { label: KIND, id: "base_shape_pod" },
          ]}
        />
        <MeterCard
          title="Thinking off"
          note="4-bit weights, on a Mac"
          meters={[
            { label: RAN, id: "base_render_mac" },
            { label: KIND, id: "base_shape_mac" },
          ]}
        />
      </div>
      <p className={`mt-3 ${MEASURE} ${CAPTION}`}>
        Both cards show the base model with no fine-tuning, scored on the same chart questions.
      </p>
      <div className="mt-8">
        <Lede>
          Most of the gap between the two cards is the thinking. With it on, the model writes out its reasoning before
          any code, and the app cannot run prose. With it off, most of its code ran, but it drew the kind of chart
          asked for less than half the time. Fine-tuning had to teach it to choose and build the right chart.
        </Lede>
      </div>
    </Section>
  );
}
