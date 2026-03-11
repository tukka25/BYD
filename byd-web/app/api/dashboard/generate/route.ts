import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as { prompt?: string };
    const prompt = body.prompt?.trim();
    if (!prompt) {
      return NextResponse.json({ detail: "Prompt is required" }, { status: 400 });
    }

    const backendUrl =
      process.env.BACKEND_API_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://localhost:8000";

    const response = await fetch(`${backendUrl}/api/v1/dashboard/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
      cache: "no-store",
    });

    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json(
      {
        detail:
          "Cannot reach backend API. Start backend on port 8000 or set BACKEND_API_URL in byd-web environment.",
      },
      { status: 503 },
    );
  }
}

