"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { backendBaseUrl, fetchCurrentUser } from "@/lib/backend";
import { loadCurrentUser, saveSession } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loadCurrentUser()) router.replace("/");
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password.trim()) return;

    setIsSubmitting(true);
    setError(null);
    const baseUrl = backendBaseUrl();

    try {
      let loginResponse = await fetch(`${baseUrl}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!loginResponse.ok) {
        const registerResponse = await fetch(`${baseUrl}/api/v1/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, full_name: name || "User" }),
        });
        if (!registerResponse.ok && registerResponse.status !== 409) {
          const body = (await registerResponse.json().catch(() => null)) as
            | { detail?: string }
            | null;
          throw new Error(body?.detail ?? "Failed to register user");
        }
        loginResponse = await fetch(`${baseUrl}/api/v1/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
      }

      if (!loginResponse.ok) {
        const body = (await loginResponse.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? "Failed to login");
      }

      const tokenData = (await loginResponse.json()) as { access_token: string };
      const user = await fetchCurrentUser(tokenData.access_token);
      saveSession(user, tokenData.access_token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to login");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#dbeafe_0%,#f8fafc_45%,#f8fafc_100%)] px-6 py-10 text-zinc-900">
      <div className="mx-auto max-w-md rounded-3xl border border-zinc-200 bg-white/90 p-8 shadow-xl backdrop-blur">
        <h1 className="font-heading text-3xl font-bold">Welcome to PromptDash</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Sign in to access your personal data sources and dashboards.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium">Name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Abdalrahman"
              className="h-11 w-full rounded-xl border border-zinc-300 px-3 text-sm outline-none ring-blue-500/30 transition focus:ring-4"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com"
              className="h-11 w-full rounded-xl border border-zinc-300 px-3 text-sm outline-none ring-blue-500/30 transition focus:ring-4"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium">Password</span>
            <input
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter any password"
              className="h-11 w-full rounded-xl border border-zinc-300 px-3 text-sm outline-none ring-blue-500/30 transition focus:ring-4"
            />
          </label>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="h-11 w-full rounded-xl bg-blue-600 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
