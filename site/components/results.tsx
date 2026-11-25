import { Num } from "@/components/num";
import { stat } from "@/components/numbers";
import { CAPTION, MEASURE, Section } from "@/components/section";

type Row = { measure: string; ids: [string | null, string, string] };

/* The page's one table of figures: the same tests before and after each
   adapter. Every value comes from data/stats.json and links to its source. */
const GROUPS: Array<{ test: string; rows: Row[] }> = [
  {
    test: `${stat("test_questions")} frozen chart questions, 4-bit on a Mac`,
    rows: [
      { measure: "Chart scripts that run", ids: ["base_render_mac", "v1_render_mac", "v2_render_mac"] },
      { measure: "Charts of the right kind", ids: ["base_shape_mac", "v1_shape_mac", "v2_shape_mac"] },
    ],
  },
  {
    test: `${stat("plan_requests")} frozen dashboard requests`,
    rows: [
      { measure: "Plans that needed a retry", ids: [null, "plan_retry_v1", "plan_retry_v2"] },
      { measure: "Drawn charts that render", ids: [null, "plan_render_v1", "plan_render_v2"] },
      { measure: "Drawn as the planned kind", ids: [null, "plan_kind_v1", "plan_kind_v2"] },
    ],
  },
];

const cell = "px-2.5 py-3 sm:px-4";

export function Results() {
  return (
    <Section id="results" title="Measured on questions it never saw">
      <div className="max-w-3xl overflow-x-auto rounded-[var(--r-card)] bg-surface shadow-[var(--lift-1)]">
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
            <tbody key={group.test} className="border-b last:border-0">
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
      <ul className={`mt-5 space-y-2 ${MEASURE} ${CAPTION}`}>
        <li>
          Base is Qwen3.5-9B with no adapter and thinking off, its best setting. With thinking on, it answers in prose,
          and nearly every script fails before it runs.
        </li>
        <li>The base model was not run on the dashboard requests.</li>
        <li>
          The dashboard requests use tables kept out of training, and the first three charts of each dashboard are
          drawn and scored.
        </li>
        <li>Every number links to the file that recorded it.</li>
      </ul>
    </Section>
  );
}
