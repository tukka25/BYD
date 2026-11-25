import { DASHBOARDS } from "@/components/dashboards";
import { AUTHOR, REPO_URL } from "@/lib/site";

const link = "underline decoration-hairline-strong underline-offset-2 hover:text-ink";

export function Footer() {
  return (
    <footer className="mt-10 border-t">
      <div className="mx-auto max-w-6xl space-y-3 px-4 py-10 text-[13px] leading-relaxed text-muted sm:px-8">
        <p>
          Built by{" "}
          <a href={AUTHOR.url} className={link}>
            {AUTHOR.handle}
          </a>
          . Base model: Qwen3.5-9B.{" "}
          <a href={REPO_URL} className={link}>
            The code is on GitHub
          </a>
          .
        </p>
        <ul className="space-y-1">
          {DASHBOARDS.map((dashboard) => (
            <li key={dashboard.name}>
              <span className="text-body">{dashboard.title}:</span>{" "}
              {[...new Set(dashboard.sources.map((source) => source.note))].join(" ")}{" "}
              {[...new Set(dashboard.sources.map((source) => source.licence))].join(", ")}.
            </li>
          ))}
        </ul>
      </div>
    </footer>
  );
}
