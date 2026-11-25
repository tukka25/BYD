import Link from "next/link";
import { DASHBOARDS } from "@/components/dashboards";
import { KeepDates } from "@/components/section";
import { capitalise, creditLine, licences } from "@/lib/dashboard";
import { AUTHOR, REPO_URL } from "@/lib/site";

const link = "underline decoration-hairline-strong underline-offset-2 hover:text-ink";

/* Who built it and whose data the dashboards draw. Each dashboard credits its
   data once and each licence once, read from the dashboard files. */
export function Footer() {
  return (
    <footer className="mt-10 border-t">
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-10 text-[14px] leading-[1.6] text-body sm:px-8">
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
        <ul className="max-w-[48rem] space-y-1.5">
          {DASHBOARDS.map((dashboard) => (
            <li key={dashboard.name}>
              <Link href={`/dashboards/${dashboard.name}/`} className={`font-semibold text-ink ${link}`}>
                {dashboard.title}
              </Link>
              : <KeepDates text={creditLine(dashboard.sources)} />{" "}
              {licences(dashboard.sources).map((licence, index) => (
                <span key={licence.licence}>
                  {index > 0 ? " " : ""}
                  {licence.licence_url ? (
                    <a href={licence.licence_url} className={link}>
                      {capitalise(licence.licence)}
                    </a>
                  ) : (
                    capitalise(licence.licence)
                  )}
                  .
                </span>
              ))}
            </li>
          ))}
        </ul>
      </div>
    </footer>
  );
}
