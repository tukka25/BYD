import { Num } from "@/components/num";
import { stat } from "@/components/numbers";
import { Section } from "@/components/section";

type Row = { measure: string; ids: [string | null, string, string] };

export function Results() {
  const groups: Array<{ test: string; rows: Row[] }> = [
    {
      test: `Frozen ${stat("test_questions")} questions, 4-bit on a Mac`,
      rows: [
        { measure: "Chart scripts that run", ids: ["base_render_mac", "v1_render_mac", "v2_render_mac"] },
        { measure: "The right kind of chart", ids: ["base_shape_mac", "v1_shape_mac", "v2_shape_mac"] },
      ],
    },
    {
      test: `Frozen ${stat("test_questions")} questions, full precision`,
      rows: [
        { measure: "Chart scripts that run", ids: ["base_render_pod", "v1_render_pod", "v2_render_pod"] },
        { measure: "The right kind of chart", ids: ["base_shape_pod", "v1_shape_pod", "v2_shape_pod"] },
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
  return (
    <Section id="results" kicker="Results" title="Measured on questions it never saw">
      <div className="overflow-x-auto rounded-[var(--r-card)] bg-surface shadow-[var(--lift-1)]">
        <table className="w-full min-w-[620px] text-left text-[14px]">
          <thead>
            <tr className="border-b text-[12px] uppercase tracking-wide text-muted">
              <th className="px-4 py-3 font-semibold">Test</th>
              <th className="px-4 py-3 font-semibold">Measure</th>
              <th className="px-4 py-3 text-right font-semibold">Base</th>
              <th className="px-4 py-3 text-right font-semibold">lora-v1</th>
              <th className="px-4 py-3 text-right font-semibold">lora-v2</th>
            </tr>
          </thead>
          <tbody>
            {groups.flatMap((group) =>
              group.rows.map((row, index) => (
                <tr
                  key={`${group.test} ${row.measure}`}
                  className={index === group.rows.length - 1 ? "border-b last:border-0" : ""}
                >
                  {index === 0 ? (
                    <th scope="rowgroup" rowSpan={group.rows.length} className="px-4 py-3 align-top font-semibold text-ink">
                      {group.test}
                    </th>
                  ) : null}
                  <td className="px-4 py-3">{row.measure}</td>
                  {row.ids.map((id, column) => (
                    <td
                      key={column}
                      className={`px-4 py-3 text-right tabular ${column === 2 ? "font-semibold text-ink" : ""}`}
                    >
                      {id ? <Num id={id} /> : <span className="text-muted">not run</span>}
                    </td>
                  ))}
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
      <ul className="mt-4 space-y-1.5 text-[13px] leading-relaxed text-muted">
        <li>
          Base on the Mac runs with thinking off, its best setting. At full precision it ran with thinking on, so{" "}
          {stat("base_render_pod")} measures its essay, not its charts.
        </li>
        <li>lora-v1 against lora-v2 on the Mac, chart scripts that run: exact McNemar p = {stat("v1_v2_p")}.</li>
        <li>
          Dashboard requests: schemas kept out of training, and the first {stat("plan_drawn_per_dashboard")} charts of
          each dashboard drawn.
        </li>
        <li>Each number links to the file that recorded it.</li>
      </ul>
    </Section>
  );
}
