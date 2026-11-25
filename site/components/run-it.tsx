import { Code, Lede, Section } from "@/components/section";
import { REPO_URL, fileUrl } from "@/lib/site";

const COMMANDS = [
  `git clone ${REPO_URL}.git`,
  `cd ${REPO_URL.split("/").pop()}`,
  "make setup",
  "make serve-model   # terminal 1",
  "make up            # terminal 2",
  "make smoke",
].join("\n");

const link = "font-semibold text-pine underline underline-offset-2 hover:text-[var(--pine-press)]";

export function RunIt() {
  return (
    <Section id="run" title="Run it on your Mac">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-12">
        <div className="space-y-5">
          <Lede>
            The model runs on the Mac itself with mlx_lm, which needs Apple Silicon, and the app runs in Docker beside
            it. <Code>make serve-model</Code> starts the model, <Code>make up</Code> starts the app on localhost:3000,
            and <Code>make smoke</Code> checks the whole stack by drawing one real chart.
          </Lede>
          <Lede>
            Dashboards are built by the local model, so your data stays on your machine. The optional Compare models
            page also runs the same question on Claude.
          </Lede>
          <Lede>
            The{" "}
            <a href={fileUrl("README.md")} className={link}>
              README
            </a>{" "}
            has the setup, and{" "}
            <a href={fileUrl("AGENTS.md")} className={link}>
              AGENTS.md
            </a>{" "}
            the measured decisions behind it.
          </Lede>
        </div>
        <pre className="self-start overflow-x-auto rounded-[var(--r-card)] bg-inverse p-5 font-mono text-[14px] leading-[1.7] text-on-dark sm:p-6">
          <code>{COMMANDS}</code>
        </pre>
      </div>
    </Section>
  );
}
