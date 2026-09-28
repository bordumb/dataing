/**
 * Test doubles for the network: a routed fetch stub and a controllable
 * EventSource. Both exercise the real API client code.
 */

import { vi } from "vitest";

export interface RecordedRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
}

export interface StubResponse {
  status?: number;
  body?: unknown;
}

type Responder =
  | StubResponse
  | ((request: RecordedRequest) => StubResponse | Promise<StubResponse>);

/**
 * Stub global fetch with routes keyed by "METHOD /path" (no query string).
 * Unrouted requests answer 404 so a missing stub fails loudly in assertions.
 */
export function stubApi(routes: Record<string, Responder>) {
  const requests: RecordedRequest[] = [];
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      const method = (init?.method ?? "GET").toUpperCase();
      const request: RecordedRequest = {
        method,
        path: url.pathname,
        query: url.searchParams,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      };
      requests.push(request);
      const responder = routes[`${method} ${url.pathname}`];
      const response =
        typeof responder === "function"
          ? await responder(request)
          : (responder ?? { status: 404, body: { detail: "Not stubbed" } });
      const status = response.status ?? 200;
      return new Response(
        status === 204 ? null : JSON.stringify(response.body ?? {}),
        { status, headers: { "Content-Type": "application/json" } },
      );
    },
  );
  vi.stubGlobal("fetch", fetchMock);

  return {
    requests,
    /** Requests matching a method and path. */
    find: (method: string, path: string) =>
      requests.filter((r) => r.method === method && r.path === path),
  };
}

type Listener = (event: MessageEvent<string>) => void;

/** EventSource double: tests push server events with `emit`. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];

  static reset() {
    FakeEventSource.instances = [];
  }

  static latest(): FakeEventSource {
    const last =
      FakeEventSource.instances[FakeEventSource.instances.length - 1];
    if (!last) throw new Error("No EventSource was opened");
    return last;
  }

  readonly url: string;
  closed = false;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  private listeners = new Map<string, Set<Listener>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }

  close() {
    this.closed = true;
  }

  open() {
    this.onopen?.(new Event("open"));
  }

  emit(type: string, data: unknown, id?: string) {
    const event = new MessageEvent(type, {
      data: JSON.stringify(data),
      lastEventId: id ?? "",
    });
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }

  fail() {
    this.onerror?.(new Event("error"));
  }
}

/** Stubs for Radix primitives (Select, DropdownMenu) under jsdom. */
export function stubRadixDom() {
  const proto = Element.prototype as unknown as Record<string, unknown>;
  proto.hasPointerCapture ??= () => false;
  proto.releasePointerCapture ??= () => undefined;
  proto.setPointerCapture ??= () => undefined;
  proto.scrollIntoView ??= () => undefined;
  const g = globalThis as unknown as Record<string, unknown>;
  g.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
