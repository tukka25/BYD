import type { ReactNode } from "react";
import { stat } from "@/components/numbers";
import { Lede, Section } from "@/components/section";

const code = (text: string) => <code className="font-mono text-[12.5px]">{text}</code>;

export function Problem() {
  const rows: Array<[ReactNode, string, string]> = [
    [<>ends with {code("print(fig.to_json())")}</>, stat("scraped_json_print"), "every time"],
    [<>calls {code("fig.show()")}</>, stat("scraped_show"), "never"],
    ["reads a file or URL", stat("scraped_reads"), "never"],
    ["the prompt names the columns", stat("scraped_columns"), "every time"],
  ];
  return (
    <Section id="problem" kicker="The problem" title="A capable model that writes essays, not charts">
      <div className="grid gap-8 lg:grid-cols-2 lg:gap-12">
        <div className="space-y-4">
          <Lede>
            Out of the box, Qwen3.5-9B opens every answer with a reasoning essay. On the {stat("test_questions")} frozen
            test questions, at full precision, {stat("base_render_pod")} of its chart scripts run.
          </Lede>
          <Lede>
            With thinking off it writes code: on a Mac at 4-bit, {stat("base_render_mac")} of its scripts run and{" "}
            {stat("base_shape_mac")} draw the right kind of chart. Most of the rest fail at run time or ask for columns
            that do not exist.
          </Lede>
          <Lede>
            And the examples to hand taught the opposite of what the app needs: {stat("scraped_rows")} rows scraped from
            plotly.com/python, measured against the app&apos;s contract.
          </Lede>
        </div>
        <div className="self-start overflow-x-auto rounded-[var(--r-card)] bg-surface shadow-[var(--lift-1)]">
          <table className="w-full text-left text-[14px]">
            <thead>
              <tr className="border-b text-[12px] uppercase tracking-wide text-muted">
                <th className="px-4 py-3 font-semibold">In the scraped examples</th>
                <th className="px-4 py-3 text-right font-semibold">Share</th>
                <th className="px-4 py-3 font-semibold">The app needs</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([what, share, need]) => (
                <tr key={share + need} className="border-b last:border-0">
                  <td className="px-4 py-3">{what}</td>
                  <td className="px-4 py-3 text-right font-semibold text-ink tabular">{share}</td>
                  <td className="px-4 py-3 text-muted">{need}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  );
}
