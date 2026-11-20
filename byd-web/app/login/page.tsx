"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ChartNoAxesColumn, ShieldCheck } from "lucide-react";
import { backendBaseUrl, fetchCurrentUser } from "@/lib/backend";
import { loadCurrentUser, saveSession } from "@/lib/auth";
import { fetchHealth, type LocalHealth } from "@/lib/reports";
import { Button, Field, Panel, inputClass } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<LocalHealth | null>(null);

  useEffect(() => {
    if (loadCurrentUser()) router.replace("/");
    fetchHealth().then(setHealth);
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
          throw new Error(body?.detail ?? "Could not create that account");
        }
        loginResponse = await fetch(`${baseUrl}/api/v1/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
      }

      if (!loginResponse.ok) {
        const body = (await loginResponse.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? "That email and password did not match");
      }

      const tokenData = (await loginResponse.json()) as { access_token: string };
      const user = await fetchCurrentUser(tokenData.access_token);
      saveSession(user, tokenData.access_token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center bg-canvas px-6 py-12">
      <div className="w-full max-w-[26rem]">
        <div className="mb-7 flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-[11px] bg-violet text-white">
            <ChartNoAxesColumn size={19} strokeWidth={2.75} />
          </span>
          <span className="font-display text-[21px] font-bold tracking-[-0.03em] text-ink">
            PromptDash
          </span>
        </div>

        <h1 className="font-display text-[32px] font-bold leading-[1.1] text-ink">
          Ask your data a question
        </h1>
        <p className="mt-2 text-[14.5px] leading-relaxed text-muted">
          Sign in to build reports. If this email is new, an account is created for you.
        </p>

        <Panel className="mt-6 p-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Field label="Name" hint="Only used when creating a new account." htmlFor="name">
              <input
                id="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Your name"
                autoComplete="name"
                className={inputClass}
              />
            </Field>

            <Field label="Email" htmlFor="email">
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                className={inputClass}
              />
            </Field>

            <Field label="Password" htmlFor="password">
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Your password"
                autoComplete="current-password"
                className={inputClass}
              />
            </Field>

            {error ? (
              <div className="flex items-start gap-2 rounded-[var(--r-card)] bg-coral-wash px-3.5 py-2.5 text-[13px] text-[#b5301c]">
                <AlertTriangle size={15} strokeWidth={2.5} className="mt-px shrink-0" />
                <span>{error}</span>
              </div>
            ) : null}

            <Button type="submit" variant="primary" size="lg" disabled={isSubmitting} className="mt-1">
              {isSubmitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </Panel>

        <p className="mt-5 flex items-center justify-center gap-2 text-center text-[12.5px] text-muted">
          <ShieldCheck size={14} strokeWidth={2.5} className="shrink-0 text-teal" />
          {health ? (
            <>
              <span className="font-mono">{health.model}</span> is running on this machine.
            </>
          ) : (
            "Your data and the model stay on this machine."
          )}
        </p>
      </div>
    </main>
  );
}
