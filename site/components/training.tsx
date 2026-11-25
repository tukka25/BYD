import { Code, Lede, Section } from "@/components/section";

/* From the rented GPU to the Mac, in the order the adapter travels. */
const PATH = [
  { what: "LoRA training", where: "an A100 rented on Runpod" },
  { what: "PEFT adapter", where: "what the training writes" },
  { what: "MLX adapter", where: <>translated by <Code>cloud/peft_to_mlx.py</Code></> },
  { what: "mlx_lm server", where: "the 4-bit base model with the adapter, on the Mac" },
];

export function Training() {
  return (
    <Section id="training" title="Trained on a rented A100, served on a Mac">
      <div className="space-y-5">
        <Lede>
          The plan was to train on the Mac with MLX, and it ran out of memory. Qwen3.5 mixes ordinary attention with
          linear-attention layers that keep a running state, and training stores that state for every token. The peak
          was far beyond what the Mac&apos;s GPU could hold.
        </Lede>
        <Lede>
          So both adapters were trained with LoRA, each on a single A100 rented on Runpod. The adapter leaves the linear-attention
          gates alone. Those gates scale the running state at every token, so even a small change to them compounds over a
          long answer.
        </Lede>
        <Lede>
          Training on the GPU writes a PEFT adapter, and mlx-lm loads only adapters it made itself, so a script
          translates one into the other. On the Mac, mlx_lm&apos;s server loads the 4-bit base model with the adapter
          on top, and the app&apos;s analyst, planner and chartist all call that one server.
        </Lede>
      </div>

      <ol className="mt-10 grid gap-3 rounded-[var(--r-card)] bg-surface p-5 shadow-[var(--lift-1)] sm:p-6 lg:grid-cols-4 lg:gap-8">
        {PATH.map((step, index) => (
          <li key={step.what} className="relative lg:pr-2">
            <p className="font-display text-[18px] font-semibold text-ink">{step.what}</p>
            <p className="mt-1 text-[16px] leading-snug text-body">{step.where}</p>
            {index < PATH.length - 1 ? (
              <span aria-hidden="true" className="mt-2 block text-[18px] leading-none text-pine lg:absolute lg:-right-6 lg:top-0.5 lg:mt-0">
                <span className="lg:hidden">↓</span>
                <span className="hidden lg:inline">→</span>
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </Section>
  );
}
