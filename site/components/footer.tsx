import type { ReactNode } from "react";
import { DASHBOARDS } from "@/components/dashboards";
import { GitHubMark } from "@/components/icons";
import { MEASURE } from "@/components/section";
import { LinkedInMark, RepoMark } from "@/components/social-icons";
import { creditTag, dataName, type Dashboard } from "@/lib/dashboard";
import { AUTHOR, LINKEDIN_URL, REPO_URL } from "@/lib/site";

const focus = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]";
const pill = `inline-flex min-h-11 items-center gap-2 rounded-[var(--r-pill)] bg-surface px-4 text-[14px] font-semibold text-ink shadow-[var(--lift-1)] transition-shadow hover:shadow-[var(--lift-2)] ${focus}`;
const nameLink = `inline-flex min-h-11 items-center font-semibold text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-pine ${focus}`;
const tagLink = `inline-flex min-h-11 items-center text-muted underline decoration-hairline-strong underline-offset-4 hover:text-ink ${focus}`;

function External({ href, className, children }: { href: string; className: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
    </a>
  );
}

/* One dataset: its name linked to its source page, and one short tag. Real
   data carries its licence when the licence needs naming (CC0 needs nothing);
   synthetic data, which has no source page and no licence link, gets its tag
   linked to the script that makes it. */
function Credit({ dashboard }: { dashboard: Dashboard }) {
  const [source] = dashboard.sources;
  const tag = creditTag(dashboard.sources);
  const synthetic = !source.licence_url;
  return (
    <li className="flex flex-wrap items-center gap-x-4 rounded-[var(--r-card)] bg-surface px-4 shadow-[var(--lift-1)]">
      {synthetic ? (
        <span className="inline-flex min-h-11 items-center font-semibold text-ink">{dataName(dashboard)}</span>
      ) : (
        <External href={source.url} className={nameLink}>
          {dataName(dashboard)}
        </External>
      )}
      {tag ? (
        <External href={tag.url} className={tagLink}>
          {tag.text}
        </External>
      ) : null}
    </li>
  );
}

/* Who built it, where the code is, and whose data the dashboards draw: links
   only, each read from the dashboard files. */
export function Footer() {
  return (
    <footer className="mt-10 border-t">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-8 md:grid-cols-[1fr_auto] md:items-start md:gap-16">
        <div className="space-y-4">
          <p className={`text-[14px] leading-[1.6] text-muted ${MEASURE}`}>Built by {AUTHOR.handle} on Qwen3.5-9B.</p>
          <ul className="flex flex-wrap gap-3">
            <li>
              <External href={AUTHOR.url} className={pill}>
                <GitHubMark size={18} />
                GitHub
              </External>
            </li>
            {LINKEDIN_URL ? (
              <li>
                <External href={LINKEDIN_URL} className={pill}>
                  <LinkedInMark size={18} />
                  LinkedIn
                </External>
              </li>
            ) : null}
            <li>
              <External href={REPO_URL} className={pill}>
                <RepoMark size={18} />
                Repository
              </External>
            </li>
          </ul>
        </div>
        <div className="space-y-3">
          <p className="text-[14px] leading-[1.6] text-muted">Data</p>
          <ul className="flex flex-col gap-2 text-[14px] sm:flex-row sm:flex-wrap md:flex-col">
            {DASHBOARDS.map((dashboard) => (
              <Credit key={dashboard.name} dashboard={dashboard} />
            ))}
          </ul>
        </div>
      </div>
    </footer>
  );
}
