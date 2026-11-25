import { Code, LINK, Lede, Section } from "@/components/section";
import { fileUrl } from "@/lib/site";

/* Only the commands that run after the README's setup. A fresh clone needs
   that setup first: the model's Python environment (make setup does not make
   it), the base model, a separate download, and the adapter, whose weights are
   not in the repository. */
const COMMANDS = ["make serve-model   # terminal 1", "make up            # terminal 2", "make smoke"].join("\n");

/* What the Compare models page sends is read from comparison.py (the question
   the app wrote for each chart, the column names and types, and three rows of
   the sampled table) and claude_chartist.py (on a repair, Claude's own code
   and the error). */
export function RunIt() {
  return (
    <Section id="run" title="Run it on your Mac">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-12">
        <div className="space-y-5">
          <Lede>
            The model runs on the Mac itself with mlx_lm, which needs Apple Silicon, and the app runs in Docker beside
            it.
          </Lede>
          <Lede>
            The{" "}
            <a href={fileUrl("README.md")} className={LINK}>
              README
            </a>{" "}
            walks through the setup: the model&apos;s Python environment, the base model, and where a trained adapter
            goes. The adapter&apos;s weights are not in the repository; they come from a training run like the one in
            part 2. Once it is set up, <Code>make serve-model</Code> starts the model, <Code>make up</Code> starts the
            app on localhost:3000, and <Code>make smoke</Code> checks the whole stack by drawing one real chart.
          </Lede>
          <Lede>
            Dashboards are built by the local model, so your data stays on your machine. The optional Compare models
            page sends Claude the question the app wrote for each chart, the column names and types, and a few sample
            rows, to compare its charts with the local model&apos;s. When Claude&apos;s code fails, that code goes back
            to Claude with the error.
          </Lede>
          <Lede>
            <a href={fileUrl("AGENTS.md")} className={LINK}>
              AGENTS.md
            </a>{" "}
            has the measured decisions behind it.
          </Lede>
        </div>
        <pre className="self-start overflow-x-auto rounded-[var(--r-card)] bg-inverse p-5 font-mono text-[14px] leading-[1.7] text-on-dark sm:p-6">
          <code>{COMMANDS}</code>
        </pre>
      </div>
    </Section>
  );
}
