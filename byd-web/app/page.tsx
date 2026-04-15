"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthUser, loadCurrentUser, logoutUser } from "@/lib/auth";

function DevicePreview() {
  return (
    <div className="relative mx-auto w-full max-w-[560px]">
      <div className="relative rounded-[2rem] border-4 border-[#324861] bg-[#1f2f43] p-4 shadow-[14px_16px_30px_rgba(45,52,54,0.2)]">
        <div className="relative overflow-hidden rounded-[1.5rem] border-4 border-black bg-[#090b11] p-6">
          <div className="pointer-events-none absolute inset-0 opacity-25 [background:linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.3)_50%)] [background-size:100%_4px]" />
          <div className="mb-8 flex items-center justify-between">
            <div className="flex gap-2">
              <span className="h-3 w-3 rounded-full bg-[#ff4757] shadow-[0_0_8px_rgba(255,71,87,0.8)]" />
              <span className="h-3 w-3 rounded-full bg-[#f59e0b]" />
              <span className="h-3 w-3 rounded-full bg-[#22c55e] shadow-[0_0_8px_rgba(34,197,94,0.8)]" />
            </div>
            <p className="font-mono text-xs uppercase tracking-[0.08em] text-[#1fd16f]">Connected_01</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-[#29405f] bg-[#0d1321]/90 p-4">
              <div className="h-2 w-24 rounded-full bg-[#2f4869]" />
              <div className="mt-3 h-2 w-36 rounded-full bg-[#2f4869]" />
              <div className="mt-5 h-44 rounded-md bg-[linear-gradient(180deg,#101b31_0%,#0d1424_100%)]" />
            </div>
            <div className="relative rounded-lg border border-[#29405f] bg-[#0d1321]/90 p-4">
              <div className="absolute left-1/2 top-1/2 h-14 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full border-[5px] border-[#2f4869] border-t-[#ff4757] animate-spin" />
              <div className="h-56 rounded-md border border-[#1f3046]" />
            </div>
          </div>

          <div className="mt-5 flex items-center justify-end gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff4757] shadow-[0_0_10px_rgba(255,71,87,0.8)]" />
            <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#6f7a8b]">PWR</span>
          </div>
        </div>
      </div>
      <div className="absolute -right-2 top-24 h-16 w-3 rounded-r-md bg-[#415b79]" />
      <div className="absolute -right-2 top-44 h-24 w-3 rounded-r-md bg-[#415b79]" />
    </div>
  );
}

export default function Home() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    setUser(loadCurrentUser());
    setIsHydrated(true);
  }, []);

  function handleLogout() {
    logoutUser();
    setUser(null);
    router.push("/login");
  }

  if (!isHydrated) {
    return (
      <main className="app-shell flex items-center justify-center text-foreground-muted">
        Loading...
      </main>
    );
  }

  if (!user) {
    return (
      <div className="app-shell pb-14">
        <header className="border-b border-[#bcc6d4] bg-[linear-gradient(180deg,#d8dee8_0%,#cdd6e3_100%)] shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_8px_18px_rgba(163,177,198,0.35)]">
          <div className="mx-auto flex h-[5.5rem] w-full max-w-7xl items-center gap-4 px-6">
            <div className="industrial-card flex h-11 w-11 items-center justify-center rounded-full">
              <span className="text-xl leading-none text-accent">S</span>
            </div>
            <div className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">PromptDash</div>

            <nav className="ml-auto hidden items-center gap-4 md:flex">
              <a
                className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#cfd7e3] px-4 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436] transition hover:bg-[#c5cedb]"
                href="#features"
              >
                Features
              </a>
              <a
                className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#cfd7e3] px-4 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436] transition hover:bg-[#c5cedb]"
                href="#workflow"
              >
                Workflow
              </a>
              <a
                className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#cfd7e3] px-4 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436] transition hover:bg-[#c5cedb]"
                href="#about"
              >
                About
              </a>
            </nav>
            <div className="ml-2 flex items-center gap-3">
              <Link
                href="/login"
                className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#cfd7e3] px-4 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436] transition hover:bg-[#c5cedb]"
              >
                Log In
              </Link>
              <Link
                href="/login"
                className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#adb7c4] bg-[#bcc7d6] px-4 text-xs font-bold uppercase tracking-[0.05em] text-[#2d3436] transition hover:bg-[#b4bfce]"
              >
                Sign Up
              </Link>
            </div>
          </div>
        </header>

        <main className="mx-auto grid w-full max-w-7xl items-center gap-12 px-6 pt-16 lg:grid-cols-[1fr_1fr]">
          <section>
            <div className="industrial-card inline-flex items-center gap-3 rounded-full px-5 py-2">
              <span className="h-3 w-3 animate-pulse rounded-full bg-[#22c55e] shadow-[0_0_10px_rgba(34,197,94,0.9)]" />
              <span className="font-mono text-xs font-bold uppercase tracking-[0.08em] text-[#51607a]">
                System Operational
              </span>
            </div>

            <h1 className="text-embossed mt-8 max-w-[12ch] font-heading text-5xl font-extrabold leading-[1.03] tracking-[-0.03em] text-foreground sm:text-7xl">
              Transform prompts into live dashboard
            </h1>
            <p className="mt-6 max-w-[62ch] text-lg leading-relaxed text-foreground-muted">
              PromptDash lets your team connect files and databases, generate charts from natural
              language, and build dashboard canvases in minutes.
            </p>

            <div className="mt-8 flex flex-wrap gap-4">
              <Link
                href="/login"
                className="inline-flex min-h-12 items-center justify-center rounded-lg bg-[#ff4757] px-8 text-sm font-bold uppercase tracking-[0.05em] text-white shadow-[4px_4px_10px_rgba(166,50,60,0.38),-4px_-4px_10px_rgba(255,130,140,0.35)] transition duration-200 hover:brightness-110 active:translate-y-[2px]"
              >
                Start Building
              </Link>
              <a
                href="#features"
                className="inline-flex min-h-12 items-center justify-center rounded-lg bg-[#2f5f95] px-8 text-sm font-bold uppercase tracking-[0.05em] text-white shadow-[4px_4px_10px_rgba(39,73,110,0.38),-4px_-4px_10px_rgba(109,148,194,0.35)] transition duration-200 hover:brightness-110 active:translate-y-[2px]"
              >
                See Features
              </a>
            </div>
          </section>

          <section className="lg:pl-4">
            <DevicePreview />
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="mx-auto flex h-20 w-full max-w-6xl items-center px-6">
        <div className="text-embossed font-heading text-xl font-extrabold uppercase tracking-[0.04em]">
          PromptDash
        </div>
        <nav className="ml-auto flex items-center gap-2 text-sm">
          <Link href="/dashboard/new" className="btn-industrial-secondary min-h-10 px-3 py-2 text-xs">
            Create Dashboard
          </Link>
          <Link
            href="/settings/data-sources"
            className="btn-industrial-secondary min-h-10 px-3 py-2 text-xs"
          >
            Data Sources
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="btn-industrial-secondary min-h-10 px-3 py-2 text-xs"
          >
            Logout
          </button>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-12 pt-8">
        <section className="industrial-panel industrial-panel-hover screw-corners p-8">
          <p className="label-tech">Logged in as {user.email}</p>
          <h1 className="text-embossed mt-2 max-w-3xl font-heading text-4xl font-extrabold">
            Build Your Own Dashboard
          </h1>
          <p className="mt-3 max-w-2xl text-foreground-muted">
            Manage your personal data sources from settings, then build a dashboard and generate
            charts from prompts in the canvas.
          </p>

          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/settings/data-sources"
              className="btn-industrial-secondary"
            >
              Open Data Source Settings
            </Link>
            <Link
              href="/dashboard/new"
              className="btn-industrial-primary"
            >
              Start New Dashboard
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}
