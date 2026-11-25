import { Code, Lede, Section } from "@/components/section";

export function Problem() {
  return (
    <Section id="problem" title="Out of the box, the model wrote essays">
      <div className="space-y-5">
        <Lede>
          PromptDash runs on Qwen3.5-9B. Asked for a chart, the base model answered with a &ldquo;Thinking
          Process:&rdquo; essay where the app expected bare Python, so almost nothing it wrote would run.
        </Lede>
        <Lede>
          With thinking switched off, the base model wrote code, and most of it ran. Most of the scripts that failed
          broke at run time or asked for columns the table did not have, and many that ran still drew the wrong kind of
          chart.
        </Lede>
        <Lede>
          The first training data came from Plotly&apos;s own documentation, a Scrapy crawl of plotly.com/python, and
          it taught nearly the opposite of what the app needs. Almost every example called <Code>fig.show()</Code>.
          None ended with <Code>print(fig.to_json())</Code>, the line the app reads each chart from. Nearly half
          loaded their data from a file or a URL, where the app hands the code a DataFrame. The prompts followed three
          docs-page templates and hardly ever named a column, while every question in the app arrives with its
          table&apos;s columns.
        </Lede>
      </div>
    </Section>
  );
}
