"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import {
  Cpu,
  Database,
  FileText,
  LogOut,
  Menu,
  Plus,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { getAccessToken, loadCurrentUser, logoutUser, noSession, subscribeToSession } from "@/lib/auth";
import {
  fetchHealth,
  listReports,
  subscribeToReports,
  type LocalHealth,
  type Report,
} from "@/lib/reports";
import { IconButton } from "@/components/ui";
import { Wordmark } from "@/components/logo";

/* The persistent frame: a fixed sidebar carrying the real navigation, and a
   grey canvas for whatever route is open. Reports live under one group so a
   user can keep several and move between them, which is the structure the
   reference's IA gets right. */

function NavItem({
  href,
  icon,
  children,
  active,
  muted,
  onNavigate,
}: {
  href: string;
  icon?: ReactNode;
  children: ReactNode;
  active: boolean;
  muted?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={[
        "group flex items-center gap-2.5 rounded-[var(--r-control)] px-3 py-2",
        "text-[13.5px] font-semibold transition-colors duration-150 ease-[var(--ease-out)]",
        active
          ? "bg-pine-wash text-pine"
          : muted
            ? "text-muted hover:bg-sunken hover:text-ink"
            : "text-body hover:bg-sunken hover:text-ink",
      ].join(" ")}
    >
      {icon ? <span className="shrink-0">{icon}</span> : null}
      <span className="truncate">{children}</span>
    </Link>
  );
}

function GroupLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-3 pb-1.5 pt-5 text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
      {children}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  // The session lives in localStorage. Read as an external store rather than
  // copied into state by an effect, so the shell renders the right session on
  // its first client pass and follows a sign-out in another tab.
  const user = useSyncExternalStore(subscribeToSession, loadCurrentUser, noSession);
  const [reports, setReports] = useState<Report[]>([]);
  const [health, setHealth] = useState<LocalHealth | null>(null);
  // Below lg the sidebar is a drawer: at 375px a fixed 248px rail leaves the
  // report a sliver of the screen and the title wraps to one word per line.
  const [drawer, setDrawer] = useState(false);
  const menuButton = useRef<HTMLButtonElement | null>(null);

  function closeDrawer() {
    setDrawer(false);
    menuButton.current?.focus();
  }

  useEffect(() => {
    // Read the store directly here, not the rendered `user`: during hydration
    // that is still the server snapshot (null), which would bounce a signed-in
    // visitor to /login.
    if (!loadCurrentUser()) {
      router.replace("/login");
      return;
    }

    const token = getAccessToken();
    if (token) {
      listReports(token)
        .then(setReports)
        .catch(() => setReports([]));
    }
    fetchHealth().then(setHealth);
  }, [router, pathname]);

  // A report renamed on the canvas has to show up in this list, which did not
  // make that request.
  useEffect(
    () =>
      subscribeToReports(() => {
        const token = getAccessToken();
        if (!token) return;
        listReports(token)
          .then(setReports)
          .catch(() => undefined);
      }),
    [],
  );

  if (!user) {
    return (
      <div className="grid min-h-dvh place-items-center bg-canvas">
        <div className="h-2 w-24 rounded-full generating" aria-label="Loading" />
      </div>
    );
  }

  const initials = (user.name || user.email).slice(0, 2).toUpperCase();

  return (
    <div className="app-frame flex h-dvh overflow-hidden bg-canvas">
      {drawer ? (
        <button
          aria-label="Close navigation"
          onClick={closeDrawer}
          className="fixed inset-0 z-40 bg-[rgb(18_18_22/0.45)] lg:hidden"
        />
      ) : null}

      <aside
        onKeyDown={(event) => {
          if (event.key === "Escape" && drawer) closeDrawer();
        }}
        className={[
          "flex h-dvh w-[248px] shrink-0 flex-col bg-surface",
          "fixed inset-y-0 left-0 z-50 transition-transform duration-300 ease-[var(--ease-out)]",
          drawer ? "translate-x-0 shadow-[var(--lift-2)]" : "invisible -translate-x-full",
          "lg:visible lg:static lg:z-auto lg:translate-x-0 lg:shadow-none",
        ].join(" ")}
      >
        <div className="flex justify-end px-3 pt-3 lg:hidden">
          <IconButton label="Close navigation" onClick={closeDrawer}>
            <X size={17} strokeWidth={2.25} />
          </IconButton>
        </div>
        <Link
          href="/"
          onClick={() => setDrawer(false)}
          className="flex items-center gap-2.5 px-5 pb-2 pt-6"
        >
          <Wordmark size={19} mark={26} keyline="var(--surface)" />
        </Link>

        <nav className="flex-1 overflow-y-auto px-3 pb-4">
          <GroupLabel>Reports</GroupLabel>
          <div className="flex flex-col gap-0.5">
            {reports.length === 0 ? (
              <p className="px-3 py-2 text-[13px] leading-relaxed text-muted">
                No reports yet.
              </p>
            ) : (
              reports.map((report) => (
                <NavItem
                  key={report.id}
                  href={`/reports/${report.id}`}
                  icon={<FileText size={16} strokeWidth={2.25} />}
                  active={pathname === `/reports/${report.id}`}
                  onNavigate={() => setDrawer(false)}
                >
                  {report.title}
                </NavItem>
              ))
            )}
            <NavItem
              href="/reports/new"
              icon={<Plus size={16} strokeWidth={2.25} />}
              active={pathname === "/reports/new"}
              muted
              onNavigate={() => setDrawer(false)}
            >
              New report
            </NavItem>
          </div>

          <GroupLabel>Data</GroupLabel>
          <div className="flex flex-col gap-0.5">
            <NavItem
              href="/data"
              icon={<Database size={16} strokeWidth={2.25} />}
              active={pathname.startsWith("/data")}
              onNavigate={() => setDrawer(false)}
            >
              Data sources
            </NavItem>
            <NavItem
              href="/compare"
              icon={<Cpu size={16} strokeWidth={2.25} />}
              active={pathname.startsWith("/compare")}
              onNavigate={() => setDrawer(false)}
            >
              Compare models
            </NavItem>
          </div>
        </nav>

        {/* The product's claim, shown rather than asserted. */}
        <div className="mx-3 mb-3 rounded-[var(--r-card)] bg-sunken px-3 py-3">
          <div className="flex items-center gap-2 text-[12px] font-bold text-ink">
            <ShieldCheck size={14} strokeWidth={2.25} className="text-pine" />
            Running on this machine
          </div>
          <p className="mt-1 text-[11.5px] leading-snug text-muted">
            {health ? (
              <>
                <span className="font-mono">{health.model}</span> via {health.llm_backend}. Your
                files never leave.
              </>
            ) : (
              "Checking the local model…"
            )}
          </p>
        </div>

        <div className="flex items-center gap-2.5 border-t border-hairline px-4 py-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-pine-wash text-[11px] font-bold text-pine">
            {initials}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-semibold text-ink">{user.name}</span>
            <span className="block truncate text-[11.5px] text-muted">{user.email}</span>
          </span>
          <IconButton
            label="Sign out"
            onClick={() => {
              logoutUser();
              router.replace("/login");
            }}
          >
            <LogOut size={15} strokeWidth={2.25} />
          </IconButton>
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="z-30 flex shrink-0 items-center gap-2 bg-canvas px-4 py-3 lg:hidden print:hidden">
          <IconButton label="Open navigation" ref={menuButton} onClick={() => setDrawer(true)}>
            <Menu size={18} strokeWidth={2.25} />
          </IconButton>
          <Wordmark size={15} mark={22} keyline="var(--canvas)" />
        </div>
        <main className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</main>
      </div>
    </div>
  );
}

/* A page header used by every route, so headings sit at one scale and the
   action slot is always in the same place. */
export function PageHeader({
  title,
  lead,
  actions,
}: {
  title: string;
  lead?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex shrink-0 flex-wrap items-end justify-between gap-4 px-5 pb-6 pt-6 sm:px-8 sm:pt-8">
      <div className="min-w-0">
        <h1 className="font-display text-[26px] font-bold leading-[1.1] text-ink sm:text-[34px]">
          {title}
        </h1>
        {lead ? <p className="mt-1.5 max-w-xl text-sm text-muted">{lead}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export { Sparkles };
