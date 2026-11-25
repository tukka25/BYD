import { Code, LINK, Lede, Name, Section } from "@/components/section";

const RUNPOD_URL = "https://www.runpod.io";

/* From the rented GPU to the Mac, in the order the adapter travels
   (chartist-finetune/cloud/README.md). */
const PATH = [
  { what: "LoRA training", where: "an A100 rented on Runpod" },
  { what: "PEFT adapter", where: "what the training writes" },
  { what: "MLX adapter", where: <>converted by <Code>cloud/peft_to_mlx.py</Code></> },
  { what: "mlx_lm server", where: "the 4-bit base model with the adapter, on the Mac" },
];

export function Training() {
  return (
    <Section id="training" title="2. Training">
      <div className="space-y-5">
        <Lede>
          Training on my Mac ran out of memory. Qwen3.5&apos;s linear-attention layers keep a running state for every
          token, and training needed far more than the Mac&apos;s GPU could hold.
        </Lede>
        <Lede>
          I trained each adapter instead on a single A100 GPU rented on{" "}
          <a href={RUNPOD_URL} className={LINK}>
            Runpod
          </a>
          , with LoRA and PEFT. Training writes a PEFT adapter, which mlx_lm cannot load, so a script converts it to
          MLX. On the Mac, mlx_lm&apos;s server runs the <Name>4-bit</Name> base model with the adapter on top.
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
