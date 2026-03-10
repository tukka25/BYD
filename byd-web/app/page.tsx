"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthUser, loadCurrentUser, logoutUser } from "@/lib/auth";

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
      <main className="flex min-h-screen items-center justify-center bg-zinc-50 text-zinc-600">
        Loading...
      </main>
    );
  }

  if (!user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,#dbeafe_0%,#f8fafc_45%,#f8fafc_100%)] px-6 py-10">
        <div className="max-w-xl rounded-3xl border border-zinc-200 bg-white/90 p-8 text-center shadow-xl">
          <h1 className="font-heading text-4xl font-bold text-zinc-900">PromptDash</h1>
          <p className="mt-3 text-zinc-600">
            Login first to access your own data sources and dashboards.
          </p>
          <Link
            href="/login"
            className="mt-6 inline-flex h-11 items-center rounded-xl bg-blue-600 px-6 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Go to Login
          </Link>
        </div>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#dbeafe_0%,#f8fafc_45%,#f8fafc_100%)] text-zinc-900">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center px-6">
        <div className="font-heading text-xl font-bold text-blue-700">PromptDash</div>
        <nav className="ml-auto flex items-center gap-2 text-sm">
          <Link href="/dashboard/new" className="rounded-lg px-3 py-2 hover:bg-white/70">
            Create Dashboard
          </Link>
          <Link href="/settings/data-sources" className="rounded-lg px-3 py-2 hover:bg-white/70">
            Data Sources
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 hover:bg-zinc-50"
          >
            Logout
          </button>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-12 pt-8">
        <section className="rounded-3xl border border-zinc-200 bg-white/85 p-8 shadow-xl">
          <p className="text-sm text-blue-700">Logged in as {user.email}</p>
          <h1 className="mt-2 font-heading text-4xl font-bold">Build Your Own Dashboard</h1>
          <p className="mt-3 max-w-2xl text-zinc-600">
            Manage your personal data sources from settings, then build a dashboard and generate
            charts from prompts in the canvas.
          </p>

          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/settings/data-sources"
              className="inline-flex h-11 items-center rounded-xl border border-zinc-300 bg-white px-5 text-sm font-semibold hover:bg-zinc-50"
            >
              Open Data Source Settings
            </Link>
            <Link
              href="/dashboard/new"
              className="inline-flex h-11 items-center rounded-xl bg-blue-600 px-5 text-sm font-semibold text-white hover:bg-blue-700"
            >
              Start New Dashboard
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}

