import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Used by platforms that support route handler max duration (e.g. Vercel).
export const maxDuration = 9000;

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as {
      prompt?: string;
      request_id?: string;
      data_source?: string;
    };
    const prompt = body.prompt?.trim();
    const requestId = (body.request_id || "").trim();
    const dataSource = (body.data_source || "").trim();

    // /generate requires authentication now, so the caller's bearer token has to
    // reach the backend. This proxy previously dropped it, which is why the
    // endpoint had to be left open to work at all.
    const authorization = request.headers.get("authorization");
    if (!authorization) {
      return NextResponse.json(
        { detail: "Not signed in. Sign in again and retry." },
        { status: 401 },
      );
    }
    if (!prompt) {
      return NextResponse.json({ detail: "Prompt is required" }, { status: 400 });
    }

    const timeoutMs = Number(process.env.BACKEND_GENERATE_TIMEOUT_MS ?? 900000);
    const backendUrl = (
      process.env.BACKEND_API_URL ||
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      "http://127.0.0.1:8000"
    ).trim();

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    let response: Response;
    try {
      // Important: do not retry this POST to multiple hosts, or we may start duplicate runs.
      response = await fetch(`${backendUrl}/api/v1/dashboard/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: authorization },
        body: JSON.stringify({
          prompt,
          request_id: requestId,
          // Empty string means "you decide" — the detective then ranks the
          // caller's registered sources instead of being told which to use.
          data_source: dataSource,
        }),
        cache: "no-store",
        signal: controller.signal,
      });
    } catch (err) {
      const isAbort = err instanceof Error && err.name === "AbortError";
      return NextResponse.json(
        {
          detail: isAbort
            ? `Dashboard generation timed out in frontend proxy after ${timeoutMs}ms.`
            : `Cannot reach backend API. Set BACKEND_API_URL and restart frontend. Tried: ${backendUrl} -> ${
                err instanceof Error ? `${err.name}: ${err.message}` : "Unknown error"
              }`,
        },
        { status: isAbort ? 504 : 503 },
      );
    } finally {
      clearTimeout(timeout);
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
