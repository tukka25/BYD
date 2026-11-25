import { Lede, Section } from "@/components/section";
import { REPO_URL, fileUrl } from "@/lib/site";

const COMMANDS = [
  `git clone ${REPO_URL}.git`,
  `cd ${REPO_URL.split("/").pop()}`,
  "make setup",
  "make serve-model   # terminal 1: the model",
  "make up            # terminal 2: the app, on localhost:3000",
  "make smoke         # an end-to-end check",
].join("\n");

export function RunIt() {
  return (
    <Section id="run" kicker="Run it" title="Run it on your Mac">
      <div className="grid gap-6 lg:grid-cols-2 lg:gap-12">
        <div className="space-y-4">
          <Lede>
            The model runs on the host with mlx_lm, which needs Apple Silicon; the app runs in Docker beside it. Your data
            and the model stay on your machine.
          </Lede>
          <Lede>
            The{" "}
            <a href={fileUrl("README.md")} className="text-pine underline underline-offset-2">
              README
            </a>{" "}
            has the details, and{" "}
            <a href={fileUrl("AGENTS.md")} className="text-pine underline underline-offset-2">
              AGENTS.md
            </a>{" "}
            the measured decisions behind them.
          </Lede>
        </div>
        <pre className="overflow-x-auto rounded-[var(--r-card)] bg-inverse p-5 font-mono text-[13px] leading-relaxed text-on-dark">
          <code>{COMMANDS}</code>
        </pre>
      </div>
    </Section>
  );
}
