import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Used by platforms that support route handler max duration (e.g. Vercel).
export const maxDuration = 300;

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as { prompt?: string; request_id?: string };
    const prompt = body.prompt?.trim();
    const requestId = (body.request_id || "").trim();
    if (!prompt) {
      return NextResponse.json({ detail: "Prompt is required" }, { status: 400 });
    }

    const timeoutMs = Number(process.env.BACKEND_GENERATE_TIMEOUT_MS ?? 300000);
    const backendCandidates = Array.from(
      new Set(
        [
          process.env.BACKEND_API_URL,
          process.env.NEXT_PUBLIC_API_BASE_URL,
          "http://localhost:8000",
          "http://127.0.0.1:8000",
          "http://host.docker.internal:8000",
          "http://api:8000",
        ]
          .map((v) => (v || "").trim())
          .filter(Boolean),
      ),
    );

    let response: Response | null = null;
    const errors: string[] = [];
    for (const backendUrl of backendCandidates) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      try {
        response = await fetch(`${backendUrl}/api/v1/dashboard/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt, request_id: requestId }),
          cache: "no-store",
          signal: controller.signal,
        });
        clearTimeout(timeout);
        if (response) {
          break;
        }
      } catch (err) {
        clearTimeout(timeout);
        const msg = err instanceof Error ? `${err.name}: ${err.message}` : "Unknown error";
        errors.push(`${backendUrl} -> ${msg}`);
      }
    }

    if (!response) {
      return NextResponse.json(
        {
          detail:
            "Cannot reach backend API. Set BACKEND_API_URL and restart frontend. Tried: " +
            errors.join(" | "),
        },
        { status: 503 },
      );
    }

    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
    });
  } catch (error) {
    const message = error instanceof Error ? `${error.name}: ${error.message}` : "Unknown proxy error";
    return NextResponse.json(
      {
        detail: `Dashboard proxy error: ${message}`,
      },
      { status: 503 },
    );
  }
}
