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
    <div className="app-shell px-6 py-10">
      <div className="industrial-panel screw-corners mx-auto max-w-md p-8">
        <p className="label-tech">Access Terminal</p>
        <h1 className="text-embossed mt-2 font-heading text-3xl font-extrabold">Welcome to PromptDash</h1>
        <p className="mt-2 max-w-[56ch] text-sm text-foreground-muted">
          Sign in to access your personal data sources and dashboards.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <label className="block">
            <span className="label-tech mb-1 block">Name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Abdalrahman"
              className="industrial-input"
            />
          </label>

          <label className="block">
            <span className="label-tech mb-1 block">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com"
              className="industrial-input"
            />
          </label>

          <label className="block">
            <span className="label-tech mb-1 block">Password</span>
            <input
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter any password"
              className="industrial-input"
            />
          </label>

          {error ? <p className="text-sm text-accent">{error}</p> : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="btn-industrial-primary w-full"
          >
            {isSubmitting ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
