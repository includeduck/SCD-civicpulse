/**
 * The only module that talks HTTP. Components call these functions and never
 * fetch() directly (enforced by ESLint).
 *
 * All paths are relative (/api/...): nginx proxies them to the backend in
 * every environment, so no backend URL is ever baked into the bundle (ADR 0002).
 */
import { ApiError, toApiError } from "./errors";
import type {
  Complaint,
  ComplaintCreate,
  ComplaintFilters,
  ComplaintList,
  Providers,
  Stats,
  Status,
  StatusUpdate,
} from "./types";

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "Can't reach CivicPulse right now. Check your connection and try again.");
  }
  if (!response.ok) throw await toApiError(response);
  return response;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await request(path, init)).json()) as T;
}

export function createComplaint(body: ComplaintCreate, signal?: AbortSignal): Promise<Complaint> {
  return json<Complaint>("/api/complaints", { method: "POST", body: JSON.stringify(body), signal });
}

export function listComplaints(filters: ComplaintFilters = {}, signal?: AbortSignal): Promise<ComplaintList> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null) query.set(key, String(value));
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return json<ComplaintList>(`/api/complaints${suffix}`, { signal });
}

export function updateStatus(id: string, status: Status): Promise<Complaint> {
  const body: StatusUpdate = { status };
  return json<Complaint>(`/api/complaints/${encodeURIComponent(id)}/status`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export type CacheState = "HIT" | "MISS" | "unknown";

/** Stats plus whether Redis served them, read from the X-Cache header. */
export async function getStats(): Promise<{ stats: Stats; cache: CacheState }> {
  const response = await request("/api/stats");
  const header = response.headers.get("X-Cache")?.toUpperCase();
  const cache: CacheState = header === "HIT" || header === "MISS" ? header : "unknown";
  return { stats: (await response.json()) as Stats, cache };
}

export function getProviders(): Promise<Providers> {
  return json<Providers>("/api/meta/providers");
}
