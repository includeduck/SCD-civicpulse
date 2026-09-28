import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import type { Complaint, ComplaintList } from "../src/api/types";

export function jsonResponse(body: unknown, init: { status?: number; headers?: Record<string, string> } = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
}

/** Replace fetch with a mock; each test scripts the server's answers. */
export function mockFetch() {
  const fetchMock = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function renderAt(ui: ReactElement, path = "/") {
  return render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);
}

export function complaint(overrides: Partial<Complaint> = {}): Complaint {
  return {
    id: "8c1f7a52-2f7e-4c3e-9d57-0d7a1e5b9f01",
    text: "Pipe burst ho gaya hai, paani sarak par beh raha hai",
    location: "F-8 Markaz",
    category: "water",
    priority: "high",
    status: "open",
    ai_summary: "Burst water pipe flooding the road in F-8 Markaz.",
    triaged_by: "llm:ollama",
    triage_latency_ms: 1840,
    created_at: "2026-09-27T10:00:00Z",
    updated_at: "2026-09-27T10:00:00Z",
    allowed_transitions: ["in_progress", "rejected"],
    ...overrides,
  };
}

export function page(complaints: Complaint[], overrides: Partial<ComplaintList> = {}): ComplaintList {
  return { complaints, total: complaints.length, page: 1, page_size: 20, total_pages: 1, ...overrides };
}

/** The URL and parsed body of the n-th fetch call. */
export function call(fetchMock: ReturnType<typeof mockFetch>, n = 0) {
  const [input, init] = fetchMock.mock.calls[n] ?? [];
  return { url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined };
}
