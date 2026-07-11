/**
 * Route-handler proxy: the ONLY path between the browser and FastAPI.
 *
 * Same code in dev (localhost:8000, no auth) and production (Railway URL +
 * bearer token). Phase 6 adds the Auth.js session check and X-User-Email
 * forwarding right here — components never change.
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const API_TOKEN = process.env.BACKEND_API_TOKEN;

async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const target = `${BACKEND_URL}/api/${path.join("/")}${request.nextUrl.search}`;

  const headers: Record<string, string> = {};
  const contentType = request.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;
  if (API_TOKEN) headers["authorization"] = `Bearer ${API_TOKEN}`;

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();

  try {
    // No timeout on purpose: a polite refresh legitimately takes ~30 s.
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });
    // 204/205/304 must have a null body — Response() throws otherwise,
    // which broke watchlist DELETE (backend replies 204 No Content).
    if ([204, 205, 304].includes(response.status)) {
      return new NextResponse(null, { status: response.status });
    }
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Backend niedostępny — uruchom API (port 8000)." },
      { status: 502 },
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
