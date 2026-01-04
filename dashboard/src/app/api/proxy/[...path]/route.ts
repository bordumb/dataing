import { NextResponse } from "next/server";
import { auth } from "@/auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function secureProxy(
  request: Request,
  path: string[],
  session: any
) {
  const target = `${API_BASE_URL}/${path.join("/")}${new URL(request.url).search}`;
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();

  // Forward authentication headers to backend
  const headers = new Headers();
  headers.set("Content-Type", request.headers.get("content-type") ?? "application/json");

  if (session?.accessToken) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  }

  if (session?.user?.id) {
    headers.set("X-User-ID", session.user.id);
  }

  if (session?.user?.role) {
    headers.set("X-User-Role", session.user.role);
  }

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      signal: AbortSignal.timeout(30000), // 30 second timeout
    });

    const responseBody = await response.text();
    return new NextResponse(responseBody, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch (error) {
    console.error("Proxy request failed:", error);
    return NextResponse.json(
      { error: "Proxy request failed" },
      { status: 502 }
    );
  }
}

export async function GET(request: Request, context: { params: { path: string[] } }) {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return secureProxy(request, context.params.path, session);
}

export async function POST(request: Request, context: { params: { path: string[] } }) {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return secureProxy(request, context.params.path, session);
}

export async function PUT(request: Request, context: { params: { path: string[] } }) {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return secureProxy(request, context.params.path, session);
}

export async function DELETE(request: Request, context: { params: { path: string[] } }) {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return secureProxy(request, context.params.path, session);
}
