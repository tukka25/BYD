import type { ReactNode } from "react";
import { Num } from "@/components/num";
import { CAPTION, LINK, Lede, MEASURE, Name, Section } from "@/components/section";
import { fileUrl } from "@/lib/site";

const QWEN_URL = "https://huggingface.co/Qwen/Qwen3.5-9B";
const PLOTLY_URL = "https://plotly.com/python/";

/* The base model's specs, each from a repository file the stats test reads:
   the parameter count from chartist-finetune/README.md, the layer mix from
   cloud/README.md (24 Gated DeltaNet layers; 8 attention layers with 4
   projections each), and the 4-bit download from chartist-finetune/README.md. */
const SPECS: Array<{ key: string; value: ReactNode; label: string }> = [
  {
    key: "parameters",
    value: (
      <>
        <Num id="qwen_params" />M
      </>
    ),
    label: "parameters in the language model",
  },
  {
    key: "layers",
    value: (
      <>
        <Num id="qwen_linear_layers" /> + <Num id="qwen_attention_layers" />
      </>
    ),
    label: "linear-attention and full-attention layers",
  },
  {
    key: "download",
    value: (
      <>
        <Num id="base_4bit_gb" /> GB
      </>
    ),
    label: "to download the 4-bit build the Mac runs",
  },
];

type Row = { measure: string; ids: [string | null, string, string] };

/* The page's one table of results: the same tests for the base model and each
   adapter. Every value comes from data/stats.json and links to its source. */
const GROUPS: Array<{ key: string; test: ReactNode; rows: Row[] }> = [
  {
    key: "chart",
    test: (
      <>
        <Num id="test_questions" /> chart questions
      </>
    ),
    rows: [
      { measure: "Code that ran and drew a chart", ids: ["base_render_mac", "v1_render_mac", "v2_render_mac"] },
      { measure: "Charts of the right kind", ids: ["base_shape_mac", "v1_shape_mac", "v2_shape_mac"] },
    ],
  },
  {
    key: "dashboard",
    test: (
      <>
        <Num id="plan_requests" /> dashboard requests
      </>
    ),
    rows: [
      { measure: "Plans that needed another try", ids: [null, "plan_retry_v1", "plan_retry_v2"] },
      { measure: "Code that ran and drew a chart", ids: [null, "plan_render_v1", "plan_render_v2"] },
      { measure: "Charts of the kind planned", ids: [null, "plan_kind_v1", "plan_kind_v2"] },
    ],
  },
];

const cell = "px-2.5 py-3 sm:px-4";

export function FineTuning() {
  return (
    <Section
      id="fine-tuning"
      title={
        <>
          <Name>Fine-tuning</Name> <Name>Qwen3.5-9B</Name>
        </>
      }
    >
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,21rem)] lg:gap-12">
        <div className="space-y-5">
          <Lede>
            So I fine-tuned{" "}
            <a href={QWEN_URL} className={`${LINK} whitespace-nowrap`}>
              Qwen3.5-9B
            </a>{" "}
            to write chart code in{" "}
            <a href={PLOTLY_URL} className={LINK}>
              Plotly
            </a>
            , a Python charting library.
          </Lede>
          <Lede>
            I trained LoRA adapters with Hugging Face&apos;s PEFT library. A LoRA adapter is a small set of extra
            weights that leaves the base model unchanged. They run on a Mac through MLX at <Name>4-bit</Name>; the
            Training section has the steps.
          </Lede>
          <Lede>
            I made two versions. <Name>lora-v1</Name> learned only chart code. <Name>lora-v2</Name> is one adapter for
            three jobs: the analyst, the planner and the chartist.
          </Lede>
        </div>
        <SpecCard />
      </div>

      <h3 id="results" className="mt-14 font-display text-[22px] font-semibold leading-tight sm:text-[24px]">
        Results
      </h3>
      <div className="mt-5 max-w-3xl overflow-x-auto rounded-[var(--r-card)] bg-surface shadow-[var(--lift-1)]">
        <table className="w-full text-left text-[15px] text-ink sm:text-[16px]">
          <thead>
            <tr className="border-b text-[14px] text-body">
              <th scope="col" className={`${cell} font-semibold`}>
                Measure
              </th>
              <th scope="col" className={`${cell} whitespace-nowrap text-right font-semibold`}>
                Base
              </th>
              <th scope="col" className={`${cell} whitespace-nowrap text-right font-semibold`}>
                lora-v1
              </th>
              <th scope="col" className={`${cell} whitespace-nowrap text-right font-semibold`}>
                lora-v2
              </th>
            </tr>
          </thead>
          {GROUPS.map((group) => (
            <tbody key={group.key} className="border-b last:border-0">
              <tr>
                <th
                  scope="rowgroup"
                  colSpan={4}
                  className={`${cell} bg-sunken/60 font-display text-[15px] font-semibold text-ink sm:text-[16px]`}
                >
                  {group.test}
                </th>
              </tr>
              {group.rows.map((row) => (
                <tr key={row.measure}>
                  <th scope="row" className={`${cell} font-normal`}>
                    {row.measure}
                  </th>
                  {row.ids.map((id, column) => (
                    <td
                      key={column}
                      className={`${cell} whitespace-nowrap text-right tabular ${column === 2 ? "font-semibold" : ""}`}
                    >
                      {id ? <Num id={id} /> : <span className="text-[14px] text-body">not run</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      <p className={`mt-4 ${MEASURE} ${CAPTION}`}>Every test in this table used data the models never saw in training.</p>
    </Section>
  );
}

/* The base model at a glance, beside the method. Each label comes first in
   the DOM, as a definition list wants, and shows under its number. Between
   `sm` and `lg` the card spans the column, so its figures sit in a row; from
   `lg` it is a narrow sidebar and they stack. */
function SpecCard() {
  return (
    <div className="self-start rounded-[var(--r-card)] bg-surface p-5 shadow-[var(--lift-1)] sm:p-6">
      <p className="font-display text-[17px] font-semibold leading-snug text-ink">The base model</p>
      <dl className="mt-4 grid gap-4 sm:grid-cols-3 sm:gap-6 lg:grid-cols-1 lg:gap-4">
        {SPECS.map((spec) => (
          <div key={spec.key} className="flex flex-col-reverse">
            <dt className="mt-1.5 text-[15px] leading-snug text-body">{spec.label}</dt>
            <dd className="whitespace-nowrap font-display text-[24px] font-bold leading-none text-ink">
              {spec.value}
            </dd>
          </div>
        ))}
      </dl>
      <p className={`mt-5 ${CAPTION}`}>
        From{" "}
        <a href={fileUrl("chartist-finetune/README.md")} className={LINK}>
          chartist-finetune/README.md
        </a>{" "}
        and{" "}
        <a href={fileUrl("chartist-finetune/cloud/README.md")} className={LINK}>
          cloud/README.md
        </a>
        .
      </p>
    </div>
  );
}
